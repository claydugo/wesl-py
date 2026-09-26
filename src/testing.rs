use std::{
    borrow::Cow,
    collections::{HashMap, HashSet},
    path::PathBuf,
};

use pyo3::{
    buffer::PyBuffer,
    exceptions::PyValueError,
    prelude::*,
    types::{PyMapping, PyTuple},
};
use wesl::{
    EscapeMangler, FileResolver, ModulePath, ResolveError, Resolver, Router, SourceMap,
    SourceMapper, SyntaxUtil, VirtualResolver,
    eval::{Context, Instance, LiteralInstance, SyntaxUtil as _, Type, ty_eval_ty},
};
use wesl_quote::{quote_declaration, quote_expression};
use wgsl_parse::SyntaxNode;
use wgsl_parse::syntax::{
    AssignmentOperator, AssignmentStatement, Attribute, BinaryExpression, BinaryOperator,
    CompoundStatement, DeclarationKind, Expression, FormalParameter, Function, FunctionCall,
    FunctionCallStatement, GlobalDeclaration, Ident, IfClause, IfStatement, ImportContent,
    LiteralExpression, NamedComponentExpression, PathOrigin, Span, Spanned, Statement, Struct,
    StructMember, TemplateArg, TranslationUnit, TypeExpression, WorkgroupSizeAttribute,
};

use crate::{Diagnostic, Failure, Features, ModuleResolver, ProjectResolver, module_path};

#[pyclass(frozen, module = "wesl._native")]
pub(super) struct TestLayout {
    result_type: Type,
    #[pyo3(get)]
    buffer_size: u32,
}

#[pymethods]
impl TestLayout {
    #[pyo3(signature = (data: "collections.abc.Buffer"))]
    fn decode(&self, data: &Bound<'_, PyAny>) -> PyResult<TestResult> {
        let buffer = PyBuffer::<u8>::get(data)?.to_vec(data.py())?;
        let Some(Instance::Struct(result)) = Instance::from_buffer(&buffer, &self.result_type)
        else {
            return Err(PyValueError::new_err("cannot decode shader test result"));
        };
        let scalar = |name| match result.member(name) {
            Some(Instance::Literal(LiteralInstance::U32(value))) => Ok(*value),
            _ => Err(PyValueError::new_err(
                "shader test result requires a u32 member",
            )),
        };
        let [actual, expected] = ["actual_bits", "expected_bits"].map(|name| {
            let Some(Instance::Vec(vector)) = result.member(name) else {
                return Err(PyValueError::new_err(
                    "shader test result requires a vector member",
                ));
            };
            vector
                .iter()
                .map(|component| match component {
                    Instance::Literal(LiteralInstance::U32(value)) => Ok(*value),
                    _ => Err(PyValueError::new_err(
                        "shader test result requires u32 components",
                    )),
                })
                .collect::<PyResult<Vec<_>>>()
        });
        Ok(TestResult {
            passed: scalar("passed")?,
            failures: scalar("failCount")?,
            value_kind: scalar("value_kind")?,
            components: scalar("components")?,
            actual: actual?,
            expected: expected?,
            site: scalar("site")?,
            completed: scalar("completed")?,
            checks: scalar("checks")?,
        })
    }
}

#[pyclass(frozen, module = "wesl._native")]
pub(super) struct TestResult {
    #[pyo3(get)]
    passed: u32,
    #[pyo3(get)]
    failures: u32,
    value_kind: u32,
    components: u32,
    actual: Vec<u32>,
    expected: Vec<u32>,
    #[pyo3(get)]
    site: u32,
    #[pyo3(get)]
    completed: u32,
    #[pyo3(get)]
    checks: u32,
}

#[pymethods]
impl TestResult {
    #[getter]
    fn values<'py>(&self, py: Python<'py>) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
        let [actual, expected] = [&self.actual, &self.expected].map(|value| -> PyResult<_> {
            match self.value_kind {
                0 => Ok((value[0] != 0).into_pyobject(py)?.to_owned().into_any()),
                1 => Ok(value[0].into_pyobject(py)?.into_any()),
                _ if self.components == 1 => {
                    Ok(f32::from_bits(value[0]).into_pyobject(py)?.into_any())
                }
                _ => {
                    let components = usize::try_from(self.components)
                        .map_err(|error| PyValueError::new_err(error.to_string()))?;
                    let values = value.get(..components).ok_or_else(|| {
                        PyValueError::new_err("shader assertion has too many components")
                    })?;
                    Ok(PyTuple::new(py, values.iter().copied().map(f32::from_bits))?.into_any())
                }
            }
        });
        Ok((actual?, expected?))
    }
}

#[derive(FromPyObject)]
pub(super) struct TestOptions<'py> {
    strip: bool,
    lower: bool,
    validate: bool,
    features: Features<'py>,
}

struct TestResolver<R> {
    inner: R,
    root: ModulePath,
    test_name: String,
    entry_point: String,
    result_module: ModulePath,
    result_binding: u32,
}

impl<R: Resolver> Resolver for TestResolver<R> {
    fn canonical_path(&self, path: &ModulePath) -> ModulePath {
        self.inner.canonical_path(path)
    }

    fn resolve_source<'a>(&'a self, path: &ModulePath) -> Result<Cow<'a, str>, ResolveError> {
        self.inner.resolve_source(path)
    }

    fn display_name(&self, path: &ModulePath) -> Option<String> {
        self.inner.display_name(path)
    }

    #[expect(
        clippy::too_many_lines,
        reason = "Apply test transformations after source mapping in one resolver."
    )]
    fn resolve_module(&self, path: &ModulePath) -> Result<TranslationUnit, ResolveError> {
        if matches!(&path.origin, PathOrigin::Package(name) if name.ends_with("/wgsl_test")) {
            return Err(ResolveError::Error(
                wesl::Error::Custom(
                    "shader tests do not support scoped wgsl_test overrides".to_owned(),
                )
                .diagnostic()
                .with_module_path(path.clone(), self.display_name(path)),
            ));
        }
        let mut syntax = self.inner.resolve_module(path)?;
        if path == &self.result_module {
            let mut pending: Vec<_> = syntax.global_declarations.iter_mut().collect();
            while let Some(declaration) = pending.pop() {
                match &mut **declaration {
                    GlobalDeclaration::Compound(compound) => pending.extend(&mut compound.body),
                    GlobalDeclaration::Declaration(declaration)
                        if declaration.ident.name().as_str() == "testResult" =>
                    {
                        for attribute in &mut declaration.attributes {
                            if let Attribute::Binding(binding) = &mut **attribute {
                                *binding = Expression::from(self.result_binding).into();
                            }
                        }
                    }
                    GlobalDeclaration::Struct(structure)
                        if structure.ident.name().as_str() == "TestResult" =>
                    {
                        if let GlobalDeclaration::Struct(additions) = quote_declaration!(
                            struct TestResult {
                                value_kind: u32,
                                components: u32,
                                actual_bits: vec4u,
                                expected_bits: vec4u,
                                site: u32,
                                completed: u32,
                                checks: u32,
                            }
                        ) {
                            structure.members.extend(additions.members);
                        }
                    }
                    _ => {}
                }
            }
        }
        if path != &self.root {
            return Ok(syntax);
        }
        let test_name = &self.test_name;
        let mut wrapper = quote_declaration! {
            @compute @workgroup_size(1) fn wesl_test_entry() {
                wgsl_test::TestResult::initTestResult();
                #test_name();
                wgsl_test::TestResult::testResult.completed = 1u;
            }
        };
        if let GlobalDeclaration::Function(function) = &mut wrapper {
            function.ident = Ident::new(self.entry_point.clone());
        }
        syntax.global_declarations.push(wrapper.into());
        syntax.retarget_idents();
        Ok(syntax)
    }
}

#[pyfunction]
#[pyo3(signature = (source, filename, features: "wesl.Features | None"=None))]
pub(super) fn discover_tests(
    py: Python<'_>,
    source: String,
    filename: String,
    features: Option<Features<'_>>,
) -> PyResult<Vec<(String, usize, usize)>> {
    let features = features.map(wesl::Features::try_from).transpose()?;
    py.detach(move || {
        let conditional = features.is_some();
        let syntax: TranslationUnit = if let Some(features) = features {
            let root = module_path("package::main")?;
            let mut resolver = VirtualResolver::new();
            resolver.add_module(root.clone(), source.as_str().into());
            wesl::compile(
                &root,
                &resolver,
                &wesl::NoMangler,
                &wesl::CompileOptions {
                    imports: false,
                    strip: false,
                    lower: false,
                    validate: false,
                    features,
                    ..Default::default()
                },
            )
            .map(|compiled| compiled.syntax)
            .map_err(|error| error.diagnostic())
        } else {
            source.parse().map_err(wesl::Diagnostic::from)
        }
        .map_err(|mut diagnostic| {
            diagnostic.detail.source = Some(source);
            diagnostic.detail.display_name = Some(filename);
            Failure::from_diagnostic(diagnostic)
        })?;
        let mut pending: Vec<_> = syntax.global_declarations.iter().collect();
        let mut tests = Vec::new();
        while let Some(declaration) = pending.pop() {
            match &**declaration {
                GlobalDeclaration::Function(function) => {
                    if function.attributes.iter().any(|attribute| {
                        matches!(&**attribute, Attribute::Custom(custom) if custom.name == "test")
                    }) {
                        let range = declaration.span().range();
                        tests.push((function.ident.name().to_string(), range.start, range.end));
                    }
                }
                GlobalDeclaration::Compound(compound) if !conditional => {
                    pending.extend(&compound.body);
                }
                _ => {}
            }
        }
        tests.sort_by_key(|test| test.1);
        Ok(tests)
    })
    .map_err(|failure: Failure| failure.into_pyerr(py))
}

type CompiledTest = Option<(
    String,
    String,
    Vec<Diagnostic>,
    HashMap<String, String>,
    TestLayout,
)>;

#[pyfunction]
#[pyo3(signature = (modules: "collections.abc.Mapping[str, str]", root, test_name, options: "wesl.TestOptions", filenames, root_directory, result_binding, dependencies, dependency_aliases=None))]
#[expect(
    clippy::too_many_arguments,
    clippy::too_many_lines,
    clippy::cognitive_complexity,
    reason = "The binding compiles and instruments one shader while detached from Python"
)]
pub(super) fn compile_test(
    py: Python<'_>,
    modules: &Bound<'_, PyMapping>,
    root: String,
    test_name: String,
    options: TestOptions<'_>,
    filenames: HashMap<String, String>,
    root_directory: Option<PathBuf>,
    result_binding: u32,
    dependencies: HashMap<String, PathBuf>,
    dependency_aliases: Option<HashMap<String, String>>,
) -> PyResult<CompiledTest> {
    let modules = modules.items()?.extract::<Vec<(String, String)>>()?;
    let TestOptions {
        strip,
        lower,
        validate,
        features,
    } = options;
    let features: wesl::Features = features.try_into()?;
    py.detach(move || {
        let root = module_path(&root)?;
        let mut dependency_resolver = Router::new();
        for (name, directory) in &dependencies {
            let path = module_path(name)?;
            if !path.origin.is_package() || !path.components.is_empty() {
                return Err(Failure::Path(name.clone()));
            }
            dependency_resolver.mount_resolver(path, FileResolver::new(directory));
        }
        let mut resolver = ModuleResolver {
            modules: VirtualResolver::new(),
            filenames: filenames
                .into_iter()
                .map(|(path, filename)| module_path(&path).map(|path| (path, filename)))
                .collect::<Result<_, _>>()?,
            files: root_directory.map(FileResolver::new),
            dependencies: dependency_resolver,
            dependency_names: dependencies.into_keys().collect(),
            dependency_aliases,
        };
        for (path, source) in modules {
            let path = module_path(&path)?;
            resolver.modules.add_module(path, source.into());
        }
        let syntax = resolver
            .resolve_module(&root)
            .map_err(|error| Failure::from_diagnostic(wesl::Diagnostic::from(error)))?;
        let mut pending: Vec<_> = syntax.global_declarations.iter().collect();
        let mut names = Vec::new();
        let mut test_exists = false;
        while let Some(declaration) = pending.pop() {
            if let Some(ident) = declaration.ident() {
                names.push(ident.name().to_string());
            }
            if let GlobalDeclaration::Function(function) = &**declaration
                && *function.ident.name() == test_name
                && function.attributes.iter().any(|attribute| {
                    matches!(&**attribute, Attribute::Custom(custom) if custom.name == "test")
                })
            {
                test_exists = true;
            }
            if let GlobalDeclaration::Compound(compound) = &**declaration {
                pending.extend(&compound.body);
            }
        }
        if !test_exists {
            return Err(Failure::Message(format!(
                "shader test {test_name:?} does not exist"
            )));
        }
        let mut imports: Vec<_> = syntax.imports.iter().map(|import| &import.content).collect();
        while let Some(content) = imports.pop() {
            match content {
                ImportContent::Item(item) => names.push(
                    item.rename.as_ref().unwrap_or(&item.ident).name().to_string(),
                ),
                ImportContent::Collection(collection) => {
                    imports.extend(collection.iter().map(|import| &import.content));
                }
            }
        }
        let mut entry_point = "wesl_test_entry".to_owned();
        while names.contains(&entry_point) {
            entry_point.push('_');
        }
        let active = wesl::compile(
            &root,
            &resolver,
            &wesl::NoMangler,
            &wesl::CompileOptions {
                imports: false,
                strip: false,
                lower: false,
                validate: false,
                features: features.clone(),
                ..Default::default()
            },
        ).map_err(|error| Failure::from_diagnostic(error.diagnostic()))?;
        let Some(declaration) = active.syntax.global_declarations.iter().find(|declaration| {
            matches!(&***declaration, GlobalDeclaration::Function(function)
                if *function.ident.name() == test_name
                    && function.attributes.iter().any(|attribute| {
                        matches!(&**attribute, Attribute::Custom(custom) if custom.name == "test")
                    }))
        }) else {
            return Ok(None);
        };
        if let GlobalDeclaration::Function(function) = &**declaration
            && (!function.parameters.is_empty()
                || function.return_type.is_some()
                || function.attributes.iter().any(|attribute| attribute.is_entry_point()))
        {
            return Err(Failure::from_diagnostic(wesl::Error::Custom(
                "@test requires a function without parameters, a return value, or a shader stage".to_owned(),
            ).diagnostic().with_source(
                resolver.resolve_source(&root)
                    .map_err(|error| Failure::from_diagnostic(wesl::Diagnostic::from(error)))?
                    .into_owned(),
            ).with_module_path(root.clone(), resolver.display_name(&root))
            .with_span(declaration.span())));
        }
        let assertion_module = module_path("wgsl_test")?;
        let result_module = module_path("wgsl_test::TestResult")?;
        let mapper = SourceMapper::new(&root, &resolver, &EscapeMangler);
        let transformed = TestResolver {
            inner: ProjectResolver {
                active: resolver.dependency_aliases.is_some(),
                inner: &mapper,
            },
            root: root.clone(),
            test_name,
            entry_point: entry_point.clone(),
            result_module: result_module.clone(),
            result_binding,
        };
        let result = wesl::compile(&root, &transformed, &mapper, &wesl::CompileOptions {
            imports: true,
            condcomp: true,
            strip,
            lower: false,
            validate,
            keep: Some(vec![entry_point.clone()]),
            keep_root: false,
            mangle_root: true,
            features,
            ..Default::default()
        });
        let sourcemap = mapper.finish();
        let mut result = result.map_err(|error| Failure::from_diagnostic(
            error.diagnostic().with_sourcemap(&sourcemap).unmangle(Some(&sourcemap), Some(&EscapeMangler))
        ))?;
        let mut assertions = HashMap::new();
        let mut result_name = None;
        let mut result_type = None;
        let mut compiled_entry = None;
        let mut overrides = HashMap::new();
        let mut context = Context::new(&result.syntax);
        for declaration in &result.syntax.global_declarations {
            if let Some(ident) = declaration.ident()
                && let Some((module, name)) = sourcemap.get_decl(&ident.name())
            {
                let value_type = match &**declaration {
                    GlobalDeclaration::Function(function) if module == &assertion_module && name.starts_with("expect") => {
                        function.parameters.first().map(|parameter| &parameter.ty)
                    }
                    GlobalDeclaration::Declaration(value) if module == &result_module && name == "testResult" => value.ty.as_ref(),
                    _ => None,
                };
                let value_type = value_type
                    .map(|value_type| {
                        let mut pending = vec![(value_type, false)];
                        let mut active = HashSet::new();
                        let mut checked = HashSet::new();
                        while let Some((ty, exiting)) = pending.pop() {
                            let name = ty.ident.name().to_string();
                            if exiting {
                                active.remove(&name);
                                continue;
                            }
                            let mut expressions: Vec<_> = ty.template_args.iter().flatten()
                                .map(|argument| &*argument.expression).collect();
                            while let Some(expression) = expressions.pop() {
                                pending.extend(wesl::query!(expression.{
                                    Expression::TypeOrIdentifier,
                                    Expression::FunctionCall.ty,
                                }).map(|child| (child, false)));
                                expressions.extend(wesl::query!(expression.{
                                    Expression::Parenthesized.expression,
                                    Expression::NamedComponent.base,
                                    Expression::Indexing.{ base, index },
                                    Expression::Unary.operand,
                                    Expression::Binary.{ left, right },
                                    Expression::FunctionCall.arguments.[],
                                }).map(|child| &**child));
                            }
                            if let Some(declaration @ (GlobalDeclaration::TypeAlias(_) | GlobalDeclaration::Struct(_))) = context.source().user_decl(&name) {
                                if active.contains(&name) {
                                    return Err(wesl::Error::from(wesl::ValidateError::Cycle(name.clone(), name)));
                                }
                                if checked.insert(name.clone()) {
                                    active.insert(name);
                                    pending.push((ty, true));
                                    pending.extend(wesl::query!(declaration.{
                                        GlobalDeclaration::TypeAlias.ty,
                                        GlobalDeclaration::Struct.members.[].ty,
                                    }).map(|child| (child, false)));
                                }
                            }
                        }
                        ty_eval_ty(value_type, &mut context).map_err(wesl::Error::from)
                    })
                    .transpose()
                    .map_err(|error| Failure::from_diagnostic(
                        wesl::Diagnostic::from(error)
                            .with_module_path(module.clone(), sourcemap.get_display_name(module).map(str::to_owned))
                            .with_span(declaration.span())
                            .with_sourcemap(&sourcemap)
                    ))?;
                if module == &assertion_module && name.starts_with("expect") && matches!(&**declaration, GlobalDeclaration::Function(_)) {
                    assertions.insert(ident.name().to_string(), (name.to_owned(), value_type));
                } else if module == &result_module && name == "testResult" {
                    result_name = Some(ident.name().to_string());
                    result_type = value_type;
                } else if module == &root {
                    if name == entry_point {
                        compiled_entry = Some(ident.name().to_string());
                    }
                    if matches!(&**declaration, GlobalDeclaration::Declaration(value)
                        if value.kind == DeclarationKind::Override)
                    {
                        overrides.insert(name.to_owned(), ident.name().to_string());
                    }
                }
            }
        }
        let Some(compiled_entry) = compiled_entry else {
            return Ok(None);
        };
        let result_name = result_name.map(Ident::new).ok_or_else(|| {
            Failure::Message("shader test result is missing".to_owned())
        })?;
        let mut sites = Vec::new();
        let mut wrappers = Vec::new();
        for declaration in &mut result.syntax.global_declarations {
            let GlobalDeclaration::Function(function) = &mut **declaration else {
                continue;
            };
            function.attributes.retain(|attribute| {
                !matches!(&**attribute, Attribute::Custom(custom) if custom.name == "test")
            });
            let Some((module, _)) = sourcemap.get_decl(&function.ident.name()) else {
                continue;
            };
            if module == &assertion_module || module == &result_module {
                let assertion = assertions.get(&*function.ident.name());
                if let Some((_, parameter_type)) = assertion {
                    let Some((parameter, parameter_type)) = function.parameters.first()
                        .zip(parameter_type.as_ref())
                        .filter(|(_, parameter_type)| {
                        **parameter_type == Type::Bool
                            || function.parameters.len() >= 2
                    }) else {
                        let mut diagnostic = wesl::Error::Custom(
                            "shader assertions require a bool first parameter or at least two parameters".to_owned(),
                        ).diagnostic().with_module_path(
                            module.clone(),
                            sourcemap.get_display_name(module).map(str::to_owned),
                        ).with_span(declaration.span());
                        diagnostic.detail.source = sourcemap.get_source(module).map(str::to_owned);
                        return Err(Failure::from_diagnostic(diagnostic));
                    };
                    let (value_kind, components): (u32, u8) = match parameter_type {
                        Type::Bool => (0, 1),
                        Type::U32 => (1, 1),
                        Type::F32 => (2, 1),
                        Type::Vec(components, scalar) if **scalar == Type::F32 => (2, *components),
                        _ => return Err(Failure::from_diagnostic(
                            wesl::Error::Custom("shader assertion values require bool, u32, f32, or a vector of f32".to_owned())
                                .diagnostic()
                                .with_module_path(module.clone(), sourcemap.get_display_name(module).map(str::to_owned))
                                .with_span(declaration.span())
                                .with_sourcemap(&sourcemap)
                        )),
                    };
                    let call = Statement::FunctionCall(FunctionCallStatement {
                        attributes: Vec::new(),
                        call: FunctionCall {
                            ty: function.ident.clone().into(),
                            arguments: function.parameters.iter()
                                .map(|parameter| Expression::from(parameter.ident.clone()).into())
                                .collect(),
                        },
                    });
                    let actual = &parameter.ident;
                    let (actual, expected) = if value_kind == 0 {
                        (
                            quote_expression!(vec4u(select(0u, 1u, #actual), 0u, 0u, 0u)),
                            quote_expression!(vec4u(1u, 0u, 0u, 0u)),
                        )
                    } else {
                        let expected = &function.parameters[1].ident;
                        match components {
                            1 => (
                                quote_expression!(vec4u(bitcast<u32>(#actual), 0u, 0u, 0u)),
                                quote_expression!(vec4u(bitcast<u32>(#expected), 0u, 0u, 0u)),
                            ),
                            2 => (
                                quote_expression!(vec4u(bitcast<vec2u>(#actual), 0u, 0u)),
                                quote_expression!(vec4u(bitcast<vec2u>(#expected), 0u, 0u)),
                            ),
                            3 => (
                                quote_expression!(vec4u(bitcast<vec3u>(#actual), 0u)),
                                quote_expression!(vec4u(bitcast<vec3u>(#expected), 0u)),
                            ),
                            _ => (
                                quote_expression!(bitcast<vec4u>(#actual)),
                                quote_expression!(bitcast<vec4u>(#expected)),
                            ),
                        }
                    };
                    let components = u32::from(components);
                    let mut wrapper = quote_declaration! {
                        fn wesl_test_wrapper(wesl_test_location: u32) {
                            #stmt@call
                            #result_name.checks += 1u;
                            if #result_name.failCount > 0u {
                                if #result_name.site == 0u {
                                    #result_name.site = wesl_test_location;
                                    #result_name.value_kind = #value_kind;
                                    #result_name.components = #components;
                                    #result_name.actual_bits = #actual;
                                    #result_name.expected_bits = #expected;
                                }
                            }
                        }
                    };
                    if let GlobalDeclaration::Function(wrapper_function) = &mut wrapper {
                        wrapper_function.ident = Ident::new(format!("{}_wesl_test", function.ident));
                        wrapper_function.parameters.splice(0..0, function.parameters.iter().cloned());
                    }
                    wrappers.push(wrapper.into());
                }
                continue;
            }
            let mut pending: Vec<_> = function.body.statements.iter_mut().collect();
            while let Some(statement) = pending.pop() {
                let span = statement.span();
                if lower
                    && let Statement::For(repeated) = &mut **statement
                    && let Some(initializer) = repeated.initializer.take()
                {
                    let repeated = std::mem::replace(&mut **statement, Statement::Void);
                    **statement = Statement::Compound(CompoundStatement {
                        attributes: Vec::new(),
                        statements: vec![initializer, Spanned::new(repeated, span)],
                    });
                }
                if let Statement::FunctionCall(call) = &mut **statement {
                    let name = assertions.get(&*call.call.ty.ident.name());
                    if let Some((name, _)) = name {
                        let range = span.range();
                        sites.push(Diagnostic {
                            message: name.clone(),
                            module: Some(module.to_string()),
                            filename: sourcemap.get_display_name(module).map(str::to_owned),
                            source: sourcemap.get_source(module).map(str::to_owned),
                            span: Some((range.start, range.end)),
                        });
                        let site = u32::try_from(sites.len())
                            .map_err(|error| Failure::Message(error.to_string()))?;
                        let wrapper_name = format!("{}_wesl_test", call.call.ty.ident.name());
                        call.call.ty.ident = Ident::new(wrapper_name);
                        call.call.arguments.push(Spanned::new(
                            Expression::Literal(LiteralExpression::U32(site)), span,
                        ));
                    }
                    continue;
                }
                match &mut **statement {
                    Statement::Compound(compound) => pending.extend(&mut compound.statements),
                    Statement::If(conditional) => {
                        pending.extend(&mut conditional.if_clause.body.statements);
                        for clause in &mut conditional.else_if_clauses {
                            pending.extend(&mut clause.body.statements);
                        }
                        if let Some(clause) = &mut conditional.else_clause {
                            pending.extend(&mut clause.body.statements);
                        }
                    }
                    Statement::Switch(switch) => {
                        for clause in &mut switch.clauses {
                            pending.extend(&mut clause.body.statements);
                        }
                    }
                    Statement::Loop(repeated) => {
                        pending.extend(&mut repeated.body.statements);
                        if let Some(continuing) = &mut repeated.continuing {
                            pending.extend(&mut continuing.body.statements);
                        }
                    }
                    Statement::For(repeated) => {
                        pending.extend(&mut repeated.body.statements);
                        pending.extend(&mut repeated.initializer);
                        pending.extend(&mut repeated.update);
                    }
                    Statement::While(repeated) => pending.extend(&mut repeated.body.statements),
                    _ => {}
                }
            }
        }
        result.syntax.global_declarations.extend(wrappers);
        if lower {
            result.syntax.retarget_idents();
            wesl::lower(&mut result.syntax).map_err(|error| {
                Failure::from_diagnostic(error.diagnostic().with_sourcemap(&sourcemap))
            })?;
        }
        let result_type = result_type.ok_or_else(|| Failure::Message("shader test result type is missing".to_owned()))?;
        let buffer_size = result_type.size_of().ok_or_else(|| Failure::Message("shader test result requires a fixed buffer size".to_owned()))?;
        Ok(Some((result.to_string(), compiled_entry, sites, overrides, TestLayout { result_type, buffer_size })))
    })
    .map_err(|failure: Failure| failure.into_pyerr(py))
}
