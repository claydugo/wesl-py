use std::{
    collections::{HashMap, HashSet},
    path::PathBuf,
    sync::Arc,
};

use pyo3::{
    buffer::PyBuffer,
    exceptions::{PyNotImplementedError, PyValueError},
    prelude::*,
    types::{PyMapping, PyTuple},
};
use wesl::{
    Resolver,
    eval::{Context, Instance, LiteralInstance, SyntaxUtil as _, Type, ty_eval_ty},
    pass::{self, Visit},
    resolver::{FileResolver, Router, VirtualResolver},
    sourcemap::SourceMap,
};
use wesl_quote::{quote_declaration, quote_expression};
use wgsl_parse::SyntaxNode;
use wgsl_parse::syntax::{
    AddressSpace, AssignmentOperator, AssignmentStatement, Attribute, BinaryExpression,
    BinaryOperator, BuiltinValue, CompoundStatement, Declaration, DeclarationKind, Expression,
    FormalParameter, Function, FunctionCall, FunctionCallStatement, GlobalDeclaration, Ident,
    IfClause, IfStatement, ImportContent, LiteralExpression, ModulePath, NamedComponentExpression,
    ParenthesizedExpression, PathOrigin, Span, Spanned, Statement, StatementNode, Struct,
    StructMember, TemplateArg, TranslationUnit, TypeExpression, UnaryExpression, UnaryOperator,
    Visibility, WorkgroupSizeAttribute,
};

use crate::{Diagnostic, Failure, Features, ModuleResolver, module_path};

#[pyclass(frozen, module = "wesl._native")]
pub(super) struct TestLayout {
    result_type: Type,
    #[pyo3(get)]
    buffer_size: u32,
    cooperative: bool,
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
            passed: if self.cooperative {
                u32::from(scalar("passed")? == scalar("invocations")?)
            } else {
                scalar("passed")?
            },
            failures: scalar("failCount")?,
            value_kind: scalar("value_kind")?,
            components: scalar("components")?,
            actual: actual?,
            expected: expected?,
            site: scalar("site")?,
            completed: scalar("completed")?,
            checks: scalar("checks")?,
            invocations: if self.cooperative {
                scalar("invocations")?
            } else {
                1
            },
            invocation: if self.cooperative {
                Some(scalar("invocation")?)
            } else {
                None
            },
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
    #[pyo3(get)]
    invocations: u32,
    #[pyo3(get)]
    invocation: Option<u32>,
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
    visibility: bool,
    lower: bool,
    validate: bool,
    features: Features<'py>,
}

struct TestTransform {
    root: ModulePath,
    test_name: String,
    entry_point: String,
    result_module: ModulePath,
    result_binding: u32,
    parameters: Vec<FormalParameter>,
    workgroup_size: Option<WorkgroupSizeAttribute>,
    cooperative: bool,
    collector: Ident,
    names: Vec<String>,
}

impl TestTransform {
    #[expect(
        clippy::too_many_lines,
        clippy::cognitive_complexity,
        reason = "Keep test transformations together before upstream compilation passes."
    )]
    fn apply(&self, path: &ModulePath, syntax: &mut TranslationUnit) -> Result<(), wesl::Error> {
        if matches!(&path.origin, PathOrigin::Package(name) if name.ends_with("/wgsl_test")) {
            return Err(wesl::Error::Custom(
                "shader tests do not support scoped wgsl_test overrides".to_owned(),
            )
            .diagnostic()
            .with_module_path(path.clone(), None)
            .into());
        }
        if path == &self.result_module {
            let mut structure = None;
            let mut binding = None;
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
                        if self.cooperative {
                            binding = Some(declaration.clone());
                            declaration.attributes.clear();
                            declaration.kind =
                                DeclarationKind::Var(Some((AddressSpace::Private, None)));
                        }
                    }
                    GlobalDeclaration::Struct(result_structure)
                        if result_structure.ident.name().as_str() == "TestResult" =>
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
                            result_structure.members.extend(additions.members);
                        }
                        if self.cooperative {
                            if let GlobalDeclaration::Struct(additions) = quote_declaration!(
                                struct TestResult {
                                    invocations: u32,
                                    invocation: u32,
                                }
                            ) {
                                result_structure.members.extend(additions.members);
                            }
                            structure = Some(result_structure.clone());
                        }
                    }
                    _ => {}
                }
            }
            if let (Some(mut structure), Some(mut binding)) = (structure, binding) {
                let output = Ident::new(format!("{}_output", self.collector));
                structure.ident = Ident::new(format!("{}_result", self.collector));
                for member in &mut structure.members {
                    if matches!(
                        member.ident.name().as_str(),
                        "passed" | "failCount" | "checks" | "completed"
                    ) && let Expression::TypeOrIdentifier(member_type) =
                        quote_expression!(atomic<u32>)
                    {
                        member.ty = member_type;
                    }
                }
                binding.ident = output.clone();
                binding.ty = Some(structure.ident.clone().into());
                let mut collector = quote_declaration! {
                    fn collectTestResult(invocation: u32, invocations: u32) {
                        atomicAdd(&#output.passed, testResult.passed);
                        atomicAdd(&#output.checks, testResult.checks);
                        let previous = atomicAdd(&#output.failCount, testResult.failCount);
                        if (testResult.failCount > 0u) && (previous == 0u) {
                            #output.value_kind = testResult.value_kind;
                            #output.components = testResult.components;
                            #output.actual_bits = testResult.actual_bits;
                            #output.expected_bits = testResult.expected_bits;
                            #output.site = testResult.site;
                            #output.invocation = invocation;
                        }
                        if invocation == 0u { #output.invocations = invocations; }
                        atomicAdd(&#output.completed, 1u);
                    }
                };
                if let GlobalDeclaration::Function(function) = &mut collector {
                    function.ident = self.collector.clone();
                    function.visibility = Visibility::Public;
                }
                syntax.global_declarations.extend([
                    GlobalDeclaration::Struct(structure).into(),
                    GlobalDeclaration::Declaration(binding).into(),
                    collector.into(),
                ]);
            }
        }
        if path != &self.root {
            return Ok(());
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
            function.parameters.clone_from(&self.parameters);
            for (index, parameter) in function.parameters.iter_mut().enumerate() {
                let mut name = format!("{}_parameter_{index}", self.entry_point);
                while self.names.contains(&name) {
                    name.push('_');
                }
                parameter.ident = Ident::new(name);
            }
            if let Some(workgroup_size) = &self.workgroup_size {
                function
                    .attributes
                    .retain(|attribute| !matches!(&**attribute, Attribute::WorkgroupSize(_)));
                function
                    .attributes
                    .push(Attribute::WorkgroupSize(workgroup_size.clone()).into());
            }
            if let Statement::FunctionCall(call) = &mut *function.body.statements[1] {
                call.call.arguments = function
                    .parameters
                    .iter()
                    .map(|parameter| Expression::from(parameter.ident.clone()).into())
                    .collect();
            }
            if self.cooperative {
                let invocation = if let Some(parameter) =
                    function.parameters.iter().find(|parameter| {
                        parameter.attributes.iter().any(|attribute| {
                            matches!(
                                &**attribute,
                                Attribute::Builtin(BuiltinValue::LocalInvocationIndex)
                            )
                        })
                    }) {
                    parameter.ident.clone()
                } else {
                    let mut name = format!("{}_invocation", self.entry_point);
                    while self.names.contains(&name)
                        || function
                            .parameters
                            .iter()
                            .any(|parameter| *parameter.ident.name() == name)
                    {
                        name.push('_');
                    }
                    let identifier = Ident::new(name);
                    function.parameters.push(FormalParameter {
                        attributes: vec![
                            Attribute::Builtin(BuiltinValue::LocalInvocationIndex).into(),
                        ],
                        ident: identifier.clone(),
                        ty: Ident::new("u32".to_owned()).into(),
                    });
                    identifier
                };
                let size = self
                    .workgroup_size
                    .clone()
                    .unwrap_or(WorkgroupSizeAttribute {
                        x: Expression::from(1u32).into(),
                        y: None,
                        z: None,
                    });
                let horizontal = (*size.x).clone();
                let vertical = (*size.y.unwrap_or(Expression::from(1u32).into())).clone();
                let depth = (*size.z.unwrap_or(Expression::from(1u32).into())).clone();
                let collector = &self.collector;
                let collected = quote_declaration! {
                    fn collect() { wgsl_test::TestResult::#collector(#invocation, u32(#horizontal) * u32(#vertical) * u32(#depth)); }
                };
                if let GlobalDeclaration::Function(collected) = collected {
                    function.body.statements.extend(collected.body.statements);
                }
            }
        }
        let mut pending: Vec<_> = syntax.global_declarations.iter_mut().collect();
        while let Some(declaration) = pending.pop() {
            match &mut **declaration {
                GlobalDeclaration::Compound(compound) => pending.extend(&mut compound.body),
                GlobalDeclaration::Function(function)
                    if function.attributes.iter().any(|attribute| {
                        matches!(&**attribute, Attribute::Custom(custom) if custom.name == "test")
                    }) =>
                {
                    function.attributes.retain(|attribute| {
                        !matches!(&**attribute, Attribute::WorkgroupSize(_))
                    });
                    for parameter in &mut function.parameters {
                        parameter.attributes.retain(|attribute| {
                            !matches!(&**attribute, Attribute::Builtin(_))
                        });
                    }
                }
                _ => {}
            }
        }
        syntax.global_declarations.push(wrapper.into());
        Ok(())
    }
}

#[pyfunction]
pub(super) fn discover_tests(
    py: Python<'_>,
    source: String,
    filename: String,
) -> PyResult<Vec<(String, usize, usize)>> {
    py.detach(move || {
        let syntax = source
            .parse::<TranslationUnit>()
            .map_err(wesl::error::Diagnostic::from)
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
                GlobalDeclaration::Compound(compound) => {
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
    if options.lower {
        return Err(PyNotImplementedError::new_err("lowering is not supported"));
    }
    let modules = modules.items()?.extract::<Vec<(String, String)>>()?;
    let TestOptions {
        strip,
        visibility,
        lower: _,
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
            filenames: HashMap::new(),
            files: root_directory.map(FileResolver::new),
            dependencies: dependency_resolver,
            dependency_names: dependencies.into_keys().collect(),
            dependency_aliases,
        };
        for (path, filename) in filenames {
            let path = resolver.dependency_path(&module_path(&path)?);
            if let Some(previous) = resolver.filenames.get(&path)
                && previous != &filename
            {
                return Err(Failure::Message(format!(
                    "conflicting filenames for module {path}"
                )));
            }
            resolver.filenames.insert(path, filename);
        }
        for (path, source) in modules {
            let path = resolver.dependency_path(&module_path(&path)?);
            if let Ok(previous) = resolver.modules.get_module(&path)
                && previous != source
            {
                return Err(Failure::Message(format!(
                    "conflicting sources for module {path}"
                )));
            }
            resolver.modules.add_module(path, source.into());
        }
        let root = resolver.dependency_path(&root);
        let mut syntax = pass::load_module(&root, &resolver)
            .map_err(|error| Failure::from_diagnostic(wesl::error::Diagnostic::from(error)))?;
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
        let root_syntax = syntax.clone();
        if let Err(error) = pass::condcomp(&mut syntax, &features) {
            return Err(Failure::from_diagnostic(error.diagnostic().with_source(
                resolver.resolve_source(&root)
                    .map_err(|error| Failure::from_diagnostic(wesl::error::Diagnostic::from(error)))?
                    .into_owned(),
            ).with_module_path(root.clone(), resolver.display_name(&root))));
        }
        let Some(declaration) = syntax.global_declarations.iter().find(|declaration| {
            matches!(&***declaration, GlobalDeclaration::Function(function)
                if *function.ident.name() == test_name
                    && function.attributes.iter().any(|attribute| {
                        matches!(&**attribute, Attribute::Custom(custom) if custom.name == "test")
                    }))
        }) else {
            return Ok(None);
        };
        if let GlobalDeclaration::Function(function) = &**declaration
            && (function.parameters.iter().any(|parameter| !parameter.attributes.iter().any(|attribute| matches!(&**attribute, Attribute::Builtin(_))))
                || function.return_type.is_some()
                || function.attributes.iter().any(|attribute| attribute.is_entry_point()))
        {
            return Err(Failure::from_diagnostic(wesl::Error::Custom(
                "@test requires a function with only builtin parameters, no return value, and no shader stage".to_owned(),
            ).diagnostic().with_source(
                resolver.resolve_source(&root)
                    .map_err(|error| Failure::from_diagnostic(wesl::error::Diagnostic::from(error)))?
                    .into_owned(),
            ).with_module_path(root.clone(), resolver.display_name(&root))
            .with_span(declaration.span())));
        }
        let assertion_module = module_path("wgsl_test")?;
        let result_module = module_path("wgsl_test::TestResult")?;
        let (parameters, workgroup_size) = match &**declaration {
            GlobalDeclaration::Function(function) => (function.parameters.clone(), function.attributes.iter().find_map(|attribute| {
                if let Attribute::WorkgroupSize(size) = &**attribute { Some(size.clone()) } else { None }
            })),
            _ => return Err(Failure::Message("shader test is not a function".to_owned())),
        };
        let cooperative = !parameters.is_empty() || workgroup_size.is_some();
        let result_syntax = pass::load_module(&result_module, &resolver).map_err(|error| Failure::from_diagnostic(wesl::error::Diagnostic::from(error)))?;
        let mut pending: Vec<_> = result_syntax.global_declarations.iter().collect();
        while let Some(declaration) = pending.pop() {
            if let Some(ident) = declaration.ident() {
                names.push(ident.name().to_string());
            }
            if let GlobalDeclaration::Compound(compound) = &**declaration {
                pending.extend(&compound.body);
            }
        }
        let mut collector = "wesl_test_collect".to_owned();
        while [collector.clone(), format!("{collector}_output"), format!("{collector}_result")]
            .iter().any(|name| names.contains(name))
        { collector.push('_'); }
        let transformed = TestTransform {
            root: root.clone(),
            test_name,
            entry_point: entry_point.clone(),
            result_module: result_module.clone(),
            result_binding,
            parameters,
            workgroup_size,
            cooperative,
            collector: Ident::new(collector),
            names,
        };
        let result = crate::compiler::compile(&root, &wesl::CompileOptions {
            imports: true,
            visibility,
            condcomp: true,
            strip,
            lower: false,
            validate,
            keep: Some(vec![entry_point.clone()]),
            keep_main: false,
            mangle_main: true,
            features,
            ..Default::default()
        }, &resolver, HashMap::from([(root.clone(), root_syntax), (result_module.clone(), result_syntax)]), |path, syntax| transformed.apply(path, syntax));
        let mut result = result.map_err(|error| Failure::from_diagnostic(error.diagnostic()))?;
        let sourcemap = result.sourcemap.take();
        let mut assertions = HashMap::new();
        let mut result_name = None;
        let mut result_type = None;
        let mut compiled_entry = None;
        let mut overrides = HashMap::new();
        let mut context = Context::new(&result.syntax);
        for declaration in &result.syntax.global_declarations {
            if let Some(ident) = declaration.ident()
                && let Some(wesl::sourcemap::SourceMapEntry { path: module, name, .. }) = sourcemap.item(&ident.name())
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
                            pending.extend(Visit::<TypeExpression>::visit(ty).map(|child| (child, false)));
                            if let Some(declaration @ (GlobalDeclaration::TypeAlias(_) | GlobalDeclaration::Struct(_))) = context.source().user_decl(&name) {
                                if active.contains(&name) {
                                    return Err(wesl::Error::from(wesl::error::ValidateError::Cycle(name.clone(), name)));
                                }
                                if checked.insert(name.clone()) {
                                    active.insert(name);
                                    pending.push((ty, true));
                                    pending.extend(Visit::<TypeExpression>::visit(declaration).map(|child| (child, false)));
                                }
                            }
                        }
                        let resolved_type = ty_eval_ty(value_type, &mut context)?;
                        let mut pending = vec![&resolved_type];
                        while let Some(current_type) = pending.pop() {
                            match current_type {
                                Type::Struct(structure) => {
                                    for member in &structure.members {
                                        if member.align == Some(0) {
                                            return Err(wesl::Error::Custom(
                                                "structure members require nonzero alignment".to_owned(),
                                            ));
                                        }
                                        pending.push(&member.ty);
                                    }
                                }
                                Type::Array(element, _) => pending.push(element),
                                _ => {}
                            }
                        }
                        Ok(resolved_type)
                    })
                    .transpose()
                    .map_err(|error| Failure::from_diagnostic(
                        wesl::error::Diagnostic::from(error)
                            .with_module_path(module.clone(), sourcemap.display_name(module).map(str::to_owned))
                            .with_span(declaration.span())
                            .with_sourcemap(&sourcemap)
                    ))?;
                if module == &assertion_module && name.starts_with("expect") && matches!(&**declaration, GlobalDeclaration::Function(_)) {
                    assertions.insert(ident.name().to_string(), (name.to_owned(), value_type));
                } else if module == &result_module && name == "testResult" {
                    result_name = Some(ident.name().to_string());
                    result_type = value_type;
                } else if module == &root {
                    if *name == entry_point {
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
        let mut sources = HashMap::new();
        let mut referenced_assertions = HashSet::new();
        for declaration in &mut result.syntax.global_declarations {
            let GlobalDeclaration::Function(function) = &mut **declaration else {
                continue;
            };
            let Some(wesl::sourcemap::SourceMapEntry { path: module, .. }) = sourcemap.item(&function.ident.name()) else {
                continue;
            };
            if module == &assertion_module || module == &result_module {
                continue;
            }
            let mut pending: Vec<_> = function.body.statements.iter_mut().collect();
            while let Some(statement) = pending.pop() {
                let span = statement.span();
                if let Statement::FunctionCall(call) = &mut **statement {
                    let name = assertions.get(&*call.call.ty.ident.name());
                    if let Some((name, _)) = name {
                        referenced_assertions.insert(call.call.ty.ident.name().to_string());
                        let range = span.range();
                        sites.push(Diagnostic {
                            message: name.clone(),
                            module: Some(module.to_string()),
                            filename: sourcemap.display_name(module).map(str::to_owned),
                            source: sources.entry(module.clone()).or_insert_with(|| {
                                sourcemap.source(module).map(Arc::<str>::from)
                            }).as_ref().map(Arc::clone),
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
                pending.extend(Visit::<StatementNode>::visit_mut(&mut **statement));
            }
        }
        let mut wrappers = Vec::new();
        for declaration in &mut result.syntax.global_declarations {
            let GlobalDeclaration::Function(function) = &mut **declaration else {
                continue;
            };
            function.attributes.retain(|attribute| {
                !matches!(&**attribute, Attribute::Custom(custom) if custom.name == "test")
            });
            let Some(wesl::sourcemap::SourceMapEntry { path: module, .. }) = sourcemap.item(&function.ident.name()) else {
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
                            sourcemap.display_name(module).map(str::to_owned),
                        ).with_span(declaration.span());
                        diagnostic.detail.source = sourcemap.source(module).map(str::to_owned);
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
                                .with_module_path(module.clone(), sourcemap.display_name(module).map(str::to_owned))
                                .with_span(declaration.span())
                                .with_sourcemap(&sourcemap)
                        )),
                    };
                    if !referenced_assertions.contains(&*function.ident.name()) {
                        continue;
                    }
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
                    let mut location = "wesl_test_location".to_owned();
                    while function.parameters.iter().any(|parameter| *parameter.ident.name() == location) {
                        location.push('_');
                    }
                    let location = Ident::new(location);
                    let mut wrapper = quote_declaration! {
                        fn wesl_test_wrapper(wesl_test_location: u32) {
                            #stmt@call
                            #result_name.checks += 1u;
                            if #result_name.failCount > 0u {
                                if #result_name.site == 0u {
                                    #result_name.site = #location;
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
                        wrapper_function.parameters[0].ident = location;
                        wrapper_function.parameters.splice(0..0, function.parameters.iter().cloned());
                    }
                    wrappers.push(wrapper.into());
                }
            }
        }
        result.syntax.global_declarations.extend(wrappers);
        let result_type = result_type.ok_or_else(|| Failure::Message("shader test result type is missing".to_owned()))?;
        let buffer_size = result_type.size_of().ok_or_else(|| Failure::Message("shader test result requires a fixed buffer size".to_owned()))?;
        Ok(Some((result.to_string(), compiled_entry, sites, overrides, TestLayout { result_type, buffer_size, cooperative })))
    })
    .map_err(|failure: Failure| failure.into_pyerr(py))
}
