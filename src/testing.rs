use std::{borrow::Cow, collections::HashMap, path::PathBuf};

use pyo3::{prelude::*, types::PyMapping};
use wesl::{
    BasicSourceMap, EscapeMangler, FileResolver, Mangler, ModulePath, ResolveError, Resolver,
    SourceMap, SyntaxUtil, VirtualResolver, Wesl,
};
use wgsl_parse::{
    SyntaxNode,
    syntax::{
        Attribute, DeclarationKind, Expression, GlobalDeclaration, Ident, ImportContent,
        LiteralExpression, PathOrigin, Spanned, Statement, TranslationUnit,
    },
};

use crate::{CompileOptions, Diagnostic, Failure, ModuleResolver, module_path};

struct TestResolver {
    inner: ModuleResolver,
    root: ModulePath,
    test_name: String,
    entry_point: String,
}

impl Resolver for TestResolver {
    fn canonical_path(&self, path: &ModulePath) -> ModulePath {
        if matches!(&path.origin, PathOrigin::Package(name) if name.rsplit('/').next() == Some("wgsl_test"))
        {
            ModulePath {
                origin: PathOrigin::Package("wgsl_test".to_owned()),
                components: path.components.clone(),
            }
        } else {
            path.clone()
        }
    }

    fn resolve_source<'a>(&'a self, path: &ModulePath) -> Result<Cow<'a, str>, ResolveError> {
        self.inner.resolve_source(path)
    }

    fn display_name(&self, path: &ModulePath) -> Option<String> {
        self.inner.display_name(path)
    }

    fn resolve_module(&self, path: &ModulePath) -> Result<TranslationUnit, ResolveError> {
        let mut syntax = self.inner.resolve_module(path)?;
        if path != &self.root {
            return Ok(syntax);
        }
        let mut pending: Vec<_> = syntax.global_declarations.iter_mut().collect();
        while let Some(declaration) = pending.pop() {
            let span = declaration.span();
            if matches!(&**declaration, GlobalDeclaration::Function(function)
            if *function.ident.name() == self.test_name
                && function.attributes.iter().any(|attribute| {
                    matches!(&**attribute, Attribute::Custom(custom) if custom.name == "test")
                }))
            {
                if let GlobalDeclaration::Function(function) = &mut **declaration {
                    let mut wrapper: TranslationUnit = format!(
                        "@compute @workgroup_size(1) fn {}() {{ wgsl_test::TestResult::initTestResult(); {}(); wgsl_test::TestResult::testResult.completed = 1u; }}",
                        self.entry_point, self.test_name,
                    ).parse().map_err(|error| ResolveError::Error(wesl::Diagnostic::from(error)))?;
                    let mut conditions: Vec<_> = function
                        .attributes
                        .iter()
                        .filter(|attribute| attribute.is_condcomp())
                        .cloned()
                        .collect();
                    if conditions.is_empty() {
                        conditions.push(Spanned::new(
                            Attribute::If(Spanned::new(
                                Expression::Literal(LiteralExpression::Bool(true)),
                                span,
                            )),
                            span,
                        ));
                    }
                    function
                        .attributes
                        .retain(|attribute| !attribute.is_condcomp());
                    let original = declaration.clone();
                    *declaration = Spanned::new(
                        GlobalDeclaration::Compound(
                            wgsl_parse::syntax::CompoundGlobalDeclaration {
                                attributes: conditions,
                                body: vec![original, wrapper.global_declarations.remove(0)],
                            },
                        ),
                        span,
                    );
                }
            } else if let GlobalDeclaration::Compound(compound) = &mut **declaration {
                pending.extend(&mut compound.body);
            }
        }
        syntax.retarget_idents();
        Ok(syntax)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn selected_test_and_entry_point_share_conditional_attributes()
    -> Result<(), Box<dyn std::error::Error>> {
        let root: ModulePath = "package::main".parse()?;
        let mut inner = ModuleResolver {
            modules: VirtualResolver::new(),
            filenames: HashMap::new(),
            files: None,
        };
        inner.modules.add_module(
            root.clone(),
            "@if(enabled) @test fn selected() {}".to_owned().into(),
        );
        let resolver = TestResolver {
            inner,
            root: root.clone(),
            test_name: "selected".to_owned(),
            entry_point: "entry".to_owned(),
        };

        let syntax = resolver.resolve_module(&root)?;
        let source = syntax.to_string();

        if !source.contains("@if(enabled)") {
            return Err("conditional attribute is missing".into());
        }
        if !source.contains("@test") || !source.contains("fn selected()") {
            return Err("selected test is missing".into());
        }
        if !source.contains("@compute @workgroup_size(1)") || !source.contains("fn entry()") {
            return Err("compute entry point is missing".into());
        }
        if !source.contains("wgsl_test::TestResult::initTestResult();")
            || !source.contains("selected();")
            || !source.contains("wgsl_test::TestResult::testResult.completed = 1u;")
        {
            return Err("test tracking calls are missing from the wrapper".into());
        }
        Ok(())
    }

    #[test]
    fn unconditional_test_gets_a_true_condition() -> Result<(), Box<dyn std::error::Error>> {
        let root: ModulePath = "package::main".parse()?;
        let mut inner = ModuleResolver {
            modules: VirtualResolver::new(),
            filenames: HashMap::new(),
            files: None,
        };
        inner
            .modules
            .add_module(root.clone(), "@test fn selected() {}".to_owned().into());
        let resolver = TestResolver {
            inner,
            root: root.clone(),
            test_name: "selected".to_owned(),
            entry_point: "entry".to_owned(),
        };

        let syntax = resolver.resolve_module(&root)?;

        if !syntax.to_string().contains("@if(true)") {
            return Err("unconditional test has no true condition".into());
        }
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
#[pyo3(signature = (modules, root, test_name, options, filenames, root_directory, result_binding))]
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
    options: CompileOptions<'_>,
    filenames: HashMap<String, String>,
    root_directory: Option<PathBuf>,
    result_binding: u32,
) -> PyResult<CompiledTest> {
    let modules = modules.items()?.extract::<Vec<(String, String)>>()?;
    let mut options = wesl::CompileOptions::try_from(options)?;
    py.detach(move || {
        if !options.imports || !options.condcomp {
            return Err(Failure::Message(
                "shader tests require imports and conditional translation".to_owned(),
            ));
        }
        let root = module_path(&root)?;
        let mut resolver = ModuleResolver {
            modules: VirtualResolver::new(),
            filenames: filenames
                .into_iter()
                .map(|(path, filename)| module_path(&path).map(|path| (path, filename)))
                .collect::<Result<_, _>>()?,
            files: root_directory.map(FileResolver::new),
        };
        for (path, source) in modules {
            let path = module_path(&path)?;
            if matches!(&path.origin, PathOrigin::Package(name) if name.rsplit('/').next() == Some("wgsl_test")) {
                return Err(Failure::Message(
                    "wgsl_test is reserved for shader assertions".to_owned(),
                ));
            }
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
        let assertion_module = module_path("wgsl_test")?;
        resolver.modules.add_module(
            assertion_module.clone(),
            include_str!("../python/wesl/wgsl_test/lib.wesl").into(),
        );
        let result_module = module_path("wgsl_test::TestResult")?;
        resolver.modules.add_module(
            result_module.clone(),
            include_str!("../python/wesl/wgsl_test/TestResult.wesl")
                .replace("@binding(0)", &format!("@binding({result_binding})"))
                .replace("expected: vec4f,", "expected: vec4f, site: u32, completed: u32, checks: u32,")
                .into(),
        );
        options.keep = Some(vec![entry_point.clone()]);
        options.keep_root = false;
        options.mangle_root = true;
        let resolver = TestResolver {
            inner: resolver,
            root: root.clone(),
            test_name: test_name.clone(),
            entry_point: entry_point.clone(),
        };
        let mut compiler = Wesl::new_barebones().set_custom_resolver(resolver);
        compiler.set_options(options);
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
        for declaration in &result.syntax.global_declarations {
            if let Some(ident) = declaration.ident()
                && let Some((module, name)) = EscapeMangler.unmangle(&ident.name())
            {
                sourcemap.add_decl(ident.name().to_string(), module, name);
            }
        }
        result.sourcemap = Some(sourcemap);
        let mut assertions = HashMap::new();
        let mut result_name = None;
        let mut compiled_entry = None;
        let mut overrides = HashMap::new();
        for declaration in &result.syntax.global_declarations {
            if let Some(ident) = declaration.ident()
                && let Some((module, name)) = result.sourcemap.get_decl(&ident.name())
            {
                if module == &assertion_module {
                    if name.starts_with("expect") {
                        assertions.insert(ident.name().to_string(), name.to_owned());
                    }
                } else if module == &result_module && name == "testResult" {
                    result_name = Some(ident.name().to_string());
                } else if module == &root {
                    if name == entry_point {
                        compiled_entry = Some(ident.name().to_string());
                    }
                    if matches!(&**declaration, GlobalDeclaration::Declaration(value)
                        if value.kind == DeclarationKind::Override)
                    {
                        overrides.insert(name.to_owned(), ident.name().to_string());
                    }
                    if name == test_name
                        && let GlobalDeclaration::Function(function) = &**declaration
                        && function.attributes.iter().any(|attribute| {
                            matches!(&**attribute, Attribute::Custom(custom) if custom.name == "test")
                        })
                        && (!function.parameters.is_empty()
                            || function.return_type.is_some()
                            || function.attributes.iter().any(|attribute| attribute.is_entry_point()))
                    {
                        return Err(Failure::from_diagnostic(wesl::Error::Custom(
                            "@test requires a function without parameters, a return value, or a shader stage".to_owned(),
                        ).diagnostic().with_source(
                            result.sourcemap.get_source(module).unwrap_or_default().to_owned(),
                        ).with_module_path(module.clone(), result.sourcemap.get_display_name(module).map(str::to_owned))
                        .with_span(declaration.span())));
                    }
                }
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
            let GlobalDeclaration::Function(function) = &mut **declaration else {
                continue;
            };
            function.attributes.retain(|attribute| {
                !matches!(&**attribute, Attribute::Custom(custom) if custom.name == "test")
            });
            let Some(module) = result
                .sourcemap
                .get_decl(&function.ident.name())
                .map(|(module, _)| module.clone())
            else {
                continue;
            };
            if module == assertion_module || module == result_module {
                if assertions.contains_key(&*function.ident.name()) {
                    let name = function.ident.name();
                    let arguments = function.parameters.iter()
                        .map(|parameter| parameter.ident.name().to_string())
                        .collect::<Vec<_>>().join(", ");
                    let mut wrapper: TranslationUnit = format!(
                        "fn {name}_wesl_test(wesl_test_location: u32) {{ {name}({arguments}); {result_name}.checks += 1u; if {result_name}.failCount > 0u && {result_name}.site == 0u {{ {result_name}.site = wesl_test_location; }} }}"
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
                            filename: result
                                .sourcemap
                                .get_display_name(&module)
                                .map(str::to_owned),
                            source: result.sourcemap.get_source(&module).map(str::to_owned),
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
