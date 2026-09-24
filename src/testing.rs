use std::{borrow::Cow, collections::HashMap, path::PathBuf};

use pyo3::{prelude::*, types::PyMapping};
use wesl::{
    BasicSourceMap, EscapeMangler, FileResolver, Mangler, ModulePath, ResolveError, Resolver,
    Router, SourceMap, SyntaxUtil, VirtualResolver, Wesl,
};
use wgsl_parse::{
    SyntaxNode,
    syntax::{
        Attribute, DeclarationKind, Expression, GlobalDeclaration, Ident, ImportContent,
        LiteralExpression, PathOrigin, Spanned, Statement, TranslationUnit,
    },
};

use crate::{Diagnostic, Failure, FeatureValue, Features, ModuleResolver, module_path};

#[derive(FromPyObject)]
pub(super) struct TestOptions<'py> {
    strip: bool,
    lower: bool,
    validate: bool,
    features: Features<'py>,
}

struct TestResolver {
    inner: ModuleResolver,
    root: ModulePath,
    test_name: String,
    entry_point: String,
}

impl Resolver for TestResolver {
    fn canonical_path(&self, path: &ModulePath) -> ModulePath {
        self.inner.canonical_path(path)
    }

    fn resolve_source<'a>(&'a self, path: &ModulePath) -> Result<Cow<'a, str>, ResolveError> {
        self.inner.resolve_source(path)
    }

    fn display_name(&self, path: &ModulePath) -> Option<String> {
        self.inner.display_name(path)
    }

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
        if path != &self.root {
            return Ok(syntax);
        }
        let wrapper: TranslationUnit = format!(
            "@compute @workgroup_size(1) fn {}() {{ wgsl_test::TestResult::initTestResult(); {}(); wgsl_test::TestResult::testResult.completed = 1u; }}",
            self.entry_point, self.test_name,
        ).parse().map_err(|error| ResolveError::Error(wesl::Diagnostic::from(error)))?;
        syntax
            .global_declarations
            .extend(wrapper.global_declarations);
        syntax.retarget_idents();
        Ok(syntax)
    }
}

#[pyfunction]
pub(super) fn discover_tests(
    py: Python<'_>,
    source: String,
    filename: String,
) -> PyResult<Vec<(String, usize, usize)>> {
    py.detach(move || {
        let syntax: TranslationUnit = source.parse().map_err(|error| {
            let mut diagnostic = wesl::Diagnostic::from(error).with_source(source);
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
                GlobalDeclaration::Compound(compound) => pending.extend(&compound.body),
                _ => {}
            }
        }
        tests.sort_by_key(|test| test.1);
        Ok(tests)
    })
    .map_err(|failure: Failure| failure.into_pyerr(py))
}

type CompiledTest = Option<(String, String, Vec<Diagnostic>, HashMap<String, String>)>;

#[pyfunction]
#[pyo3(signature = (modules, root, test_name, options, filenames, root_directory, result_binding, dependencies))]
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
) -> PyResult<CompiledTest> {
    let modules = modules.items()?.extract::<Vec<(String, String)>>()?;
    let TestOptions {
        strip,
        lower,
        validate,
        features,
    } = options;
    let features = wesl::Features {
        default: features.default.try_into()?,
        flags: features
            .flags
            .items()?
            .extract::<Vec<(String, FeatureValue)>>()?
            .into_iter()
            .map(|(name, feature)| {
                Ok((
                    name,
                    match feature {
                        FeatureValue::Flag(enabled) => enabled.into(),
                        FeatureValue::Policy(feature) => feature.try_into()?,
                    },
                ))
            })
            .collect::<PyResult<_>>()?,
    };
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
        let result_source = resolver.resolve_source(&result_module)
            .map_err(|error| Failure::from_diagnostic(wesl::Diagnostic::from(error)))?
            .replace("@binding(0)", &format!("@binding({result_binding})"))
            .replace("failCount: u32,", "failCount: u32, value_kind: u32, components: u32,")
            .replace("expected: vec4f,", "expected: vec4f, site: u32, completed: u32, checks: u32,");
        resolver.modules.add_module(result_module.clone(), result_source.into());
        let resolver = TestResolver {
            inner: resolver,
            root: root.clone(),
            test_name,
            entry_point: entry_point.clone(),
        };
        let mut compiler = Wesl::new_barebones().set_custom_resolver(resolver);
        compiler.set_options(wesl::CompileOptions {
            imports: true,
            condcomp: true,
            strip,
            lower,
            validate,
            keep: Some(vec![entry_point.clone()]),
            keep_root: false,
            mangle_root: true,
            features,
            ..Default::default()
        });
        compiler.set_mangler(wesl::ManglerKind::Escape);
        compiler.use_sourcemap(false);
        let mut result = compiler.compile(&root).map_err(|error| {
            let mut diagnostic = error.diagnostic();
            if diagnostic.detail.source.is_none()
                && let Some(module) = &diagnostic.detail.module_path
                && let Ok(source) = compiler.resolver().resolve_source(module)
            {
                diagnostic = diagnostic.with_source(source.into_owned());
            }
            Failure::from_diagnostic(diagnostic)
        })?;
        let mut sourcemap = BasicSourceMap::new();
        for module in &result.modules {
            let source = compiler
                .resolver()
                .resolve_source(module)
                .map_err(|error| Failure::from_diagnostic(wesl::Diagnostic::from(error)))?;
            sourcemap.add_source(
                module.clone(),
                compiler.resolver().display_name(module),
                source.into_owned(),
            );
        }
        let mut assertions = HashMap::new();
        let mut result_name = None;
        let mut compiled_entry = None;
        let mut overrides = HashMap::new();
        let mut aliases = HashMap::new();
        for declaration in &result.syntax.global_declarations {
            if let GlobalDeclaration::TypeAlias(alias) = &**declaration {
                aliases.insert(alias.ident.name().to_string(), alias.ty.ident.name().to_string());
            }
            if let Some(ident) = declaration.ident()
                && let Some((module, name)) = EscapeMangler.unmangle(&ident.name())
            {
                if module == assertion_module {
                    if name.starts_with("expect") {
                        assertions.insert(ident.name().to_string(), name.clone());
                    }
                } else if module == result_module && name == "testResult" {
                    result_name = Some(ident.name().to_string());
                } else if module == root {
                    if name == entry_point {
                        compiled_entry = Some(ident.name().to_string());
                    }
                    if matches!(&**declaration, GlobalDeclaration::Declaration(value)
                        if value.kind == DeclarationKind::Override)
                    {
                        overrides.insert(name.clone(), ident.name().to_string());
                    }
                }
                sourcemap.add_decl(ident.name().to_string(), module, name);
            }
        }
        let Some(compiled_entry) = compiled_entry else {
            return Ok(None);
        };
        let result_name = result_name.ok_or_else(|| {
            Failure::Message("shader test result is missing".to_owned())
        })?;
        let mut sites = Vec::new();
        let mut wrappers = Vec::new();
        for declaration in &mut result.syntax.global_declarations {
            if let GlobalDeclaration::Struct(structure) = &mut **declaration
                && sourcemap.get_decl(&structure.ident.name())
                    .is_some_and(|(module, name)| module == &result_module && name == "TestResult")
            {
                for member in &mut structure.members {
                    if matches!(member.ident.name().as_str(), "actual" | "expected") {
                        member.ty.ident = Ident::new("vec4u".to_owned());
                        member.ty.template_args = None;
                    }
                }
            }
            let GlobalDeclaration::Function(function) = &mut **declaration else {
                continue;
            };
            function.attributes.retain(|attribute| {
                !matches!(&**attribute, Attribute::Custom(custom) if custom.name == "test")
            });
            let Some((module, name)) = sourcemap.get_decl(&function.ident.name()) else {
                continue;
            };
            if module == &assertion_module || module == &result_module {
                if name == "recordFailure" {
                    function.body.statements.retain(|statement| {
                        !matches!(&**statement, Statement::If(_))
                    });
                }
                if assertions.contains_key(&*function.ident.name()) {
                    let Some((parameter, parameter_type)) = function.parameters.first().map(|parameter| {
                        let mut parameter_type = parameter.ty.ident.name().to_string();
                        for _ in 0..aliases.len() {
                            let Some(alias) = aliases.get(&parameter_type) else {
                                break;
                            };
                            parameter_type = alias.clone();
                        }
                        (parameter, parameter_type)
                    }).filter(|(_, parameter_type)| {
                        parameter_type == "bool"
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
                    let name = function.ident.name();
                    let arguments = function.parameters.iter()
                        .map(|parameter| parameter.ident.name().to_string())
                        .collect::<Vec<_>>().join(", ");
                    let components = parameter_type.strip_prefix("vec")
                        .and_then(|suffix| suffix.chars().next())
                        .and_then(|component| component.to_digit(10))
                        .unwrap_or(1);
                    let value_kind = match parameter_type.as_str() {
                        "bool" => 0,
                        "u32" => 1,
                        _ => 2,
                    };
                    let (actual, expected) = if value_kind == 0 {
                        (
                            format!("vec4u(select(0u, 1u, {}), 0u, 0u, 0u)", parameter.ident),
                            "vec4u(1u, 0u, 0u, 0u)".to_owned(),
                        )
                    } else {
                        let value_type = if components == 1 {
                            "u32".to_owned()
                        } else {
                            format!("vec{components}u")
                        };
                        let padding = ", 0u".repeat((4 - components) as usize);
                        (
                            format!("vec4u(bitcast<{value_type}>({}){padding})", parameter.ident),
                            format!("vec4u(bitcast<{value_type}>({}){padding})", function.parameters[1].ident),
                        )
                    };
                    let mut wrapper: TranslationUnit = format!(
                        "fn {name}_wesl_test(wesl_test_location: u32) {{ {name}({arguments}); {result_name}.checks += 1u; if {result_name}.failCount > 0u && {result_name}.site == 0u {{ {result_name}.site = wesl_test_location; {result_name}.value_kind = {value_kind}u; {result_name}.components = {components}u; {result_name}.actual = {actual}; {result_name}.expected = {expected}; }} }}"
                    ).parse().map_err(|error| Failure::from_diagnostic(wesl::Diagnostic::from(error)))?;
                    if let GlobalDeclaration::Function(wrapper_function) =
                        &mut *wrapper.global_declarations[0]
                    {
                        wrapper_function.parameters.splice(0..0, function.parameters.iter().cloned());
                    }
                    wrappers.extend(wrapper.global_declarations);
                }
                continue;
            }
            let mut pending: Vec<_> = function.body.statements.iter_mut().collect();
            while let Some(statement) = pending.pop() {
                let span = statement.span();
                if let Statement::FunctionCall(call) = &mut **statement {
                    let name = assertions.get(&*call.call.ty.ident.name());
                    if let Some(name) = name {
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
        Ok(Some((result.to_string(), compiled_entry, sites, overrides)))
    })
    .map_err(|failure: Failure| failure.into_pyerr(py))
}
