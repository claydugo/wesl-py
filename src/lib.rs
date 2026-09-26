use std::{
    borrow::Cow,
    collections::{BTreeMap, HashMap, HashSet},
    path::PathBuf,
};

use pyo3::{
    create_exception,
    exceptions::{PyException, PyValueError},
    prelude::*,
    types::{PyMapping, PyTuple, PyType},
};
use wesl::{
    FileResolver, ModulePath, ResolveError, Resolver, Router, SourceMap, SourceMapper,
    StandardResolver, SyntaxUtil, VirtualResolver, Wesl,
};
use wgsl_parse::{
    error::ErrorKind,
    syntax::{GlobalDeclaration, ImportContent, ImportStatement, PathOrigin, TranslationUnit},
};

mod testing;

create_exception!(
    wesl,
    CompileError,
    PyException,
    "A syntax or compilation failure. The diagnostics attribute is a tuple of Diagnostic values."
);

#[derive(FromPyObject)]
struct Feature {
    value: String,
}

impl TryFrom<Feature> for wesl::Feature {
    type Error = PyErr;

    fn try_from(feature: Feature) -> PyResult<Self> {
        match feature.value.as_str() {
            "Enable" => Ok(Self::Enable),
            "Disable" => Ok(Self::Disable),
            "Keep" => Ok(Self::Keep),
            "Error" => Ok(Self::Error),
            _ => Err(PyValueError::new_err("invalid feature policy")),
        }
    }
}

#[derive(FromPyObject)]
enum FeatureValue {
    Flag(bool),
    Policy(Feature),
}

#[derive(FromPyObject)]
struct Features<'py> {
    default: Feature,
    flags: Bound<'py, PyMapping>,
}

impl TryFrom<Features<'_>> for wesl::Features {
    type Error = PyErr;

    fn try_from(features: Features<'_>) -> PyResult<Self> {
        Ok(Self {
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
        })
    }
}

#[derive(FromPyObject)]
struct ManglerKind {
    value: String,
}

#[derive(FromPyObject)]
struct CompileOptions<'py> {
    imports: bool,
    condcomp: bool,
    strip: bool,
    lower: bool,
    validate: bool,
    sourcemap: bool,
    mangler: ManglerKind,
    mangle_root: bool,
    keep: Option<Vec<String>>,
    keep_root: bool,
    features: Features<'py>,
}

impl TryFrom<CompileOptions<'_>> for wesl::CompileOptions {
    type Error = PyErr;

    fn try_from(options: CompileOptions<'_>) -> PyResult<Self> {
        Ok(Self {
            imports: options.imports,
            condcomp: options.condcomp,
            strip: options.strip,
            lower: options.lower,
            validate: options.validate,
            mangle_root: options.mangle_root,
            keep: options.keep,
            keep_root: options.keep_root,
            features: options.features.try_into()?,
            ..Self::default()
        })
    }
}

#[pyclass(frozen, eq, hash, module = "wesl")]
#[derive(PartialEq, Eq, Hash)]
#[doc = "An immutable error value with optional source information and a UTF-8 byte range."]
struct Diagnostic {
    #[pyo3(get)]
    #[doc = "The error message without a source excerpt."]
    message: String,
    #[pyo3(get)]
    #[doc = "The WESL module name, or None when unavailable."]
    module: Option<String>,
    #[pyo3(get)]
    #[doc = "The display filename, or None when unavailable."]
    filename: Option<String>,
    #[pyo3(get)]
    #[doc = "The original source text, or None when unavailable."]
    source: Option<String>,
    #[pyo3(get)]
    #[doc = "The UTF-8 byte range (start, end), with an exclusive end, or None."]
    span: Option<(usize, usize)>,
}

#[pymethods]
impl Diagnostic {
    #[new]
    #[pyo3(signature = (message, module=None, filename=None, source=None, span=None))]
    fn new(
        message: String,
        module: Option<String>,
        filename: Option<String>,
        source: Option<String>,
        span: Option<(usize, usize)>,
    ) -> Self {
        Self {
            message,
            module,
            filename,
            source,
            span,
        }
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "Diagnostic(message={}, module={}, filename={}, span={})",
            self.message.as_str().into_pyobject(py)?.repr()?,
            self.module.as_deref().into_pyobject(py)?.repr()?,
            self.filename.as_deref().into_pyobject(py)?.repr()?,
            self.span.into_pyobject(py)?.repr()?,
        ))
    }

    #[getter]
    fn line(&self) -> Option<usize> {
        self.position(self.span?.0).map(|position| position.0)
    }

    #[getter]
    fn column(&self) -> Option<usize> {
        self.position(self.span?.0).map(|position| position.1)
    }

    #[getter]
    fn end_line(&self) -> Option<usize> {
        self.position(self.span?.1).map(|position| position.0)
    }

    #[getter]
    fn end_column(&self) -> Option<usize> {
        self.position(self.span?.1).map(|position| position.1)
    }

    fn __reduce__<'py>(
        &self,
        py: Python<'py>,
    ) -> PyResult<(Bound<'py, PyType>, Bound<'py, PyTuple>)> {
        Ok((
            py.get_type::<Self>(),
            (
                &self.message,
                &self.module,
                &self.filename,
                &self.source,
                self.span,
            )
                .into_pyobject(py)?,
        ))
    }
}

#[pyclass(frozen, eq, hash, get_all, from_py_object, module = "wesl")]
#[derive(Clone, PartialEq, Eq, Hash)]
struct Source {
    text: String,
    filename: Option<String>,
}

#[pymethods]
impl Source {
    #[new]
    #[pyo3(signature = (text, filename=None))]
    fn new(text: String, filename: Option<String>) -> Self {
        Self { text, filename }
    }

    fn __reduce__<'py>(&self, py: Python<'py>) -> (Bound<'py, PyType>, (&str, Option<&str>)) {
        (
            py.get_type::<Self>(),
            (&self.text, self.filename.as_deref()),
        )
    }
}

#[pyclass(frozen, eq, module = "wesl")]
#[derive(PartialEq, Eq)]
struct CompileResult {
    #[pyo3(get)]
    wgsl: String,
    modules: Vec<String>,
    entry_points: Vec<String>,
    #[pyo3(get)]
    sources: BTreeMap<String, Source>,
}

#[pymethods]
impl CompileResult {
    #[new]
    fn new(
        wgsl: String,
        modules: Vec<String>,
        entry_points: Vec<String>,
        sources: BTreeMap<String, Source>,
    ) -> Self {
        Self {
            wgsl,
            modules,
            entry_points,
            sources,
        }
    }

    #[getter]
    fn modules<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(py, &self.modules)
    }

    #[getter]
    fn entry_points<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyTuple>> {
        PyTuple::new(py, &self.entry_points)
    }

    fn __str__(&self) -> &str {
        &self.wgsl
    }

    fn __repr__(&self, py: Python<'_>) -> PyResult<String> {
        Ok(format!(
            "CompileResult(modules={}, entry_points={})",
            self.modules(py)?.repr()?,
            self.entry_points(py)?.repr()?,
        ))
    }

    fn __reduce__<'py>(
        &self,
        py: Python<'py>,
    ) -> PyResult<(Bound<'py, PyType>, Bound<'py, PyTuple>)> {
        Ok((
            py.get_type::<Self>(),
            (
                &self.wgsl,
                &self.modules,
                &self.entry_points,
                self.sources.clone(),
            )
                .into_pyobject(py)?,
        ))
    }
}

struct ModuleResolver {
    modules: VirtualResolver<'static>,
    filenames: HashMap<ModulePath, String>,
    files: Option<FileResolver>,
    dependencies: Router,
    dependency_names: HashSet<String>,
    dependency_aliases: Option<HashMap<String, String>>,
}

impl Resolver for ModuleResolver {
    fn canonical_path(&self, path: &ModulePath) -> ModulePath {
        if let Some(aliases) = &self.dependency_aliases {
            if let PathOrigin::Package(name) = &path.origin
                && self.modules.get_module(path).is_err()
                && let Some(canonical) = aliases
                    .get(name)
                    .map(String::as_str)
                    .or_else(|| (name.ends_with("/wgsl_test")).then_some("wgsl_test"))
            {
                return ModulePath {
                    origin: PathOrigin::Package(canonical.to_owned()),
                    components: path.components.clone(),
                };
            }
            return path.clone();
        }
        if let PathOrigin::Package(name) = &path.origin
            && !self.dependency_names.contains(name)
            && self.modules.get_module(path).is_err()
            && let Some((parent, name)) = name.rsplit_once('/')
            && let name = if parent.rsplit('/').next() == Some(name)
                && self.dependency_names.contains(parent)
            {
                parent
            } else {
                name
            }
            && self.dependency_names.contains(name)
        {
            ModulePath {
                origin: PathOrigin::Package(name.to_owned()),
                components: path.components.clone(),
            }
        } else {
            path.clone()
        }
    }

    fn resolve_source<'a>(&'a self, path: &ModulePath) -> Result<Cow<'a, str>, ResolveError> {
        match (self.modules.get_module(path), &self.files) {
            (Ok(source), _) => Ok(Cow::Borrowed(source)),
            (Err(_), _) if matches!(&path.origin, PathOrigin::Package(name) if self.dependency_names.contains(name)) =>
            {
                let mut path = path.clone();
                if path.components.is_empty() {
                    path.components.push("package".to_owned());
                }
                self.dependencies.resolve_source(&path)
            }
            (Err(_), Some(files)) if path.origin.is_absolute() => files.resolve_source(path),
            (Err(error), _) => Err(error),
        }
    }

    fn display_name(&self, path: &ModulePath) -> Option<String> {
        if self.modules.get_module(path).is_ok() {
            self.filenames.get(path).cloned()
        } else if matches!(&path.origin, PathOrigin::Package(name) if self.dependency_names.contains(name))
        {
            let mut path = path.clone();
            if path.components.is_empty() {
                path.components.push("package".to_owned());
            }
            self.dependencies.display_name(&path)
        } else {
            self.files.as_ref()?.display_name(path)
        }
    }
}

struct ProjectResolver<R> {
    inner: R,
    active: bool,
}

impl<R: Resolver> Resolver for ProjectResolver<R> {
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
        let mut syntax = self.inner.resolve_module(path)?;
        if self.active
            && let PathOrigin::Package(namespace) = &path.origin
        {
            for import in &mut syntax.imports {
                if import.path.is_none()
                    && let ImportContent::Collection(collection) = &mut import.content
                {
                    for item in collection {
                        if let Some(name) = item.path.first_mut() {
                            *name = format!("{namespace}/{name}");
                        }
                    }
                }
            }
        }
        Ok(syntax)
    }
}

impl Diagnostic {
    fn position(&self, offset: usize) -> Option<(usize, usize)> {
        let prefix = self.source.as_ref()?.get(..offset)?;
        let mut line = 1;
        let mut column = 1;
        let mut characters = prefix.chars().peekable();
        while let Some(character) = characters.next() {
            if matches!(
                character,
                '\n' | '\u{000B}' | '\u{000C}' | '\r' | '\u{0085}' | '\u{2028}' | '\u{2029}'
            ) {
                line += 1;
                column = 1;
                if character == '\r' && characters.peek() == Some(&'\n') {
                    characters.next();
                }
            } else {
                column += 1;
            }
        }
        Some((line, column))
    }
}

enum Failure {
    Message(String),
    Path(String),
    Compiler(Box<Diagnostic>, String),
}

impl Failure {
    fn from_diagnostic(mut diagnostic: wesl::Diagnostic<wesl::Error>) -> Self {
        if let wesl::Error::ParseError(error) = &mut *diagnostic.error
            && matches!(error.error, ErrorKind::UnexpectedEof { .. })
            && let Some(source) = &diagnostic.detail.source
        {
            error.span = (source.len()..source.len()).into();
            diagnostic.detail.span = Some(error.span);
        }
        if let wesl::Error::ParseError(error) = &*diagnostic.error
            && let ErrorKind::UnexpectedToken { token, .. } = &error.error
            && token == "import"
            && let Some(source) = &diagnostic.detail.source
            && let Some(prefix) = source.get(..error.span.range().start)
            && let Ok(prefix) =
                format!("{prefix}fn wesl_import_order() {{}}").parse::<TranslationUnit>()
            && (!prefix.global_directives.is_empty() || prefix.global_declarations.len() > 1)
        {
            *diagnostic.error =
                wesl::Error::Custom("imports must precede directives and declarations".to_owned());
        }
        let rendered = diagnostic.render_plain();
        let span = diagnostic.detail.span.map(|span| {
            let range = span.range();
            (range.start, range.end)
        });
        let message = match &*diagnostic.error {
            wesl::Error::ParseError(error) => error.error.to_string(),
            error => error.to_string(),
        };
        Self::Compiler(
            Box::new(Diagnostic {
                message,
                module: diagnostic
                    .detail
                    .module_path
                    .as_ref()
                    .map(ToString::to_string),
                filename: diagnostic.detail.display_name,
                source: diagnostic.detail.source,
                span,
            }),
            rendered,
        )
    }

    fn into_pyerr(self, py: Python<'_>) -> PyErr {
        match self {
            Self::Message(message) => PyValueError::new_err(message),
            Self::Path(path) => PyValueError::new_err(format!(
                "invalid module path {path:?}; expected an absolute module or package name"
            )),
            Self::Compiler(diagnostic, rendered) => {
                let error = CompileError::new_err(rendered);
                let result = Py::new(py, *diagnostic)
                    .and_then(|diagnostic| PyTuple::new(py, [diagnostic]))
                    .and_then(|diagnostics| error.value(py).setattr("diagnostics", diagnostics));
                result.err().unwrap_or(error)
            }
        }
    }
}

fn module_path(path: &str) -> Result<ModulePath, Failure> {
    let syntax_path = path.replace('/', "::");
    let statement: ImportStatement = format!("import {syntax_path}::item;")
        .parse()
        .map_err(|_| Failure::Path(path.to_owned()))?;
    let validated = statement
        .path
        .filter(|module| !module.origin.is_relative() && module.to_string() == syntax_path)
        .ok_or_else(|| Failure::Path(path.to_owned()))?;
    let module: ModulePath = path.parse().map_err(|_| Failure::Path(path.to_owned()))?;
    if module
        .components
        .iter()
        .any(|component| component.contains('/'))
        || (path.contains('/') && !validated.origin.is_package())
    {
        return Err(Failure::Path(path.to_owned()));
    }
    Ok(module)
}

#[pyfunction]
#[pyo3(signature = (modules: "collections.abc.Mapping[str, str]", root, options: "wesl.CompileOptions | None", filenames, root_directory, dependencies, dependency_aliases=None))]
#[expect(
    clippy::too_many_arguments,
    reason = "The binding accepts compiler settings and Python source inputs."
)]
#[expect(
    clippy::too_many_lines,
    reason = "Keep compiler setup and result conversion together."
)]
fn compile(
    py: Python<'_>,
    modules: &Bound<'_, PyMapping>,
    root: String,
    options: Option<CompileOptions<'_>>,
    filenames: HashMap<String, String>,
    root_directory: Option<PathBuf>,
    dependencies: HashMap<String, PathBuf>,
    dependency_aliases: Option<HashMap<String, String>>,
) -> PyResult<CompileResult> {
    let modules = modules.items()?.extract::<Vec<(String, String)>>()?;
    let sourcemap = options.as_ref().is_none_or(|options| options.sourcemap);
    let mangler = match options
        .as_ref()
        .map(|options| options.mangler.value.as_str())
    {
        Some("Escape") | None => wesl::ManglerKind::Escape,
        Some("Hash") => wesl::ManglerKind::Hash,
        Some("Unicode") => wesl::ManglerKind::Unicode,
        Some("None") => wesl::ManglerKind::None,
        _ => return Err(PyValueError::new_err("invalid mangler")),
    };
    let options = options
        .map(wesl::CompileOptions::try_from)
        .transpose()?
        .unwrap_or_default();
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
                .map(|(path, filename)| Ok((module_path(&path)?, filename)))
                .collect::<Result<_, Failure>>()?,
            files: root_directory.map(FileResolver::new),
            dependencies: dependency_resolver,
            dependency_names: dependencies.into_keys().collect(),
            dependency_aliases,
        };
        for (path, source) in modules {
            resolver
                .modules
                .add_module(module_path(&path)?, source.into());
        }
        let project = resolver.dependency_aliases.is_some();
        let result = if sourcemap && project {
            let mangler: Box<dyn wesl::Mangler> = match mangler {
                wesl::ManglerKind::Escape => Box::new(wesl::EscapeMangler),
                wesl::ManglerKind::Hash => Box::new(wesl::HashMangler),
                wesl::ManglerKind::Unicode => Box::new(wesl::UnicodeMangler),
                wesl::ManglerKind::None => Box::new(wesl::NoMangler),
            };
            let mapper = SourceMapper::new(&root, &resolver, &mangler);
            let result = wesl::compile(
                &root,
                &ProjectResolver {
                    inner: &mapper,
                    active: true,
                },
                &mapper,
                &options,
            );
            let sourcemap = mapper.finish();
            match result {
                Ok(mut result) => {
                    result.sourcemap = Some(sourcemap);
                    Ok(result)
                }
                Err(error) => Err(error
                    .diagnostic()
                    .with_sourcemap(&sourcemap)
                    .unmangle(Some(&sourcemap), Some(&mangler))
                    .into()),
            }
        } else {
            let mut compiler = Wesl::new_barebones().set_custom_resolver(ProjectResolver {
                inner: resolver,
                active: project,
            });
            compiler.set_options(options);
            compiler.set_mangler(mangler);
            compiler.use_sourcemap(sourcemap);
            compiler.compile(&root)
        };
        result
            .map(|result| CompileResult {
                wgsl: result.to_string(),
                modules: result.modules.iter().map(ToString::to_string).collect(),
                sources: result
                    .modules
                    .iter()
                    .filter_map(|module| {
                        let text = result.sourcemap.get_source(module)?;
                        Some((
                            module.to_string(),
                            Source {
                                text: text.to_owned(),
                                filename: result
                                    .sourcemap
                                    .get_display_name(module)
                                    .map(str::to_owned),
                            },
                        ))
                    })
                    .collect(),
                entry_points: result
                    .syntax
                    .entry_points()
                    .map(ToString::to_string)
                    .collect(),
            })
            .map_err(|error| Failure::from_diagnostic(error.diagnostic()))
    })
    .map_err(|failure| failure.into_pyerr(py))
}

#[pyfunction]
#[pyo3(signature = (module, constants: "collections.abc.Mapping[str, bool | int | float]"))]
fn constant_module(
    py: Python<'_>,
    module: String,
    constants: &Bound<'_, PyMapping>,
) -> PyResult<String> {
    #[derive(FromPyObject)]
    enum ConstantValue {
        Boolean(bool),
        Integer(i64),
        Float(f64),
    }

    let constants = constants
        .items()?
        .extract::<Vec<(String, ConstantValue)>>()?;
    py.detach(move || {
        let mut resolver = StandardResolver::new("");
        for (name, value) in constants {
            if name.starts_with("__")
                || !format!("const {name} = 0;")
                    .parse::<GlobalDeclaration>()
                    .is_ok_and(|declaration| {
                        matches!(declaration, GlobalDeclaration::Declaration(declaration)
                            if declaration.ident.name().as_str() == name)
                    })
            {
                return Err(Failure::Message(format!(
                    "{module}::{name}: invalid WGSL identifier"
                )));
            }
            resolver.add_constant(
                name,
                match value {
                    ConstantValue::Boolean(value) => value.into(),
                    ConstantValue::Integer(value) => value.into(),
                    ConstantValue::Float(value) => value.into(),
                },
            );
        }
        resolver
            .resolve_source(&ModulePath::new(
                PathOrigin::Package("constants".to_owned()),
                Vec::new(),
            ))
            .map(Cow::into_owned)
            .map_err(|error| Failure::from_diagnostic(wesl::Diagnostic::from(error)))
    })
    .map_err(|failure| failure.into_pyerr(py))
}

#[pyfunction]
fn render_diagnostic(py: Python<'_>, diagnostic: &Diagnostic) -> String {
    py.detach(move || {
        let mut rendered = wesl::Error::Custom(diagnostic.message.clone()).diagnostic();
        rendered.detail.module_path = diagnostic
            .module
            .as_ref()
            .and_then(|path| path.parse().ok());
        rendered
            .detail
            .display_name
            .clone_from(&diagnostic.filename);
        if let Some(source) = &diagnostic.source
            && let Some((start, end)) = diagnostic.span
            && source.get(start..end).is_some()
        {
            let mut normalized = String::with_capacity(source.len());
            let mut normalized_start = 0;
            let mut normalized_end = 0;
            let mut previous = None;
            for (offset, character) in source.char_indices() {
                if offset == start {
                    normalized_start = normalized.len();
                }
                if offset == end {
                    normalized_end = normalized.len();
                }
                match character {
                    '\n' if previous == Some('\r') => {}
                    '\r' | '\u{000B}' | '\u{000C}' | '\u{0085}' | '\u{2028}' | '\u{2029}' => {
                        normalized.push('\n');
                    }
                    _ => normalized.push(character),
                }
                previous = Some(character);
            }
            if start == source.len() {
                normalized_start = normalized.len();
            }
            if end == source.len() {
                normalized_end = normalized.len();
            }
            rendered.detail.source = Some(normalized);
            rendered.detail.span = Some((normalized_start..normalized_end).into());
        }
        rendered.render_plain()
    })
}

#[pyfunction]
fn check_syntax(py: Python<'_>, source: String, filename: String) -> PyResult<()> {
    py.detach(move || {
        source
            .parse::<TranslationUnit>()
            .map(|_| ())
            .map_err(|error| {
                let mut diagnostic = wesl::Diagnostic::from(error).with_source(source);
                diagnostic.detail.display_name = Some(filename);
                Failure::from_diagnostic(diagnostic)
            })
    })
    .map_err(|failure| failure.into_pyerr(py))
}

#[pymodule(gil_used = false)]
mod _native {
    use pyo3::{prelude::*, types::PyTuple};

    #[pymodule_export]
    use super::testing::{TestResult, compile_test, discover_tests};
    #[pymodule_export]
    use super::{
        CompileError, CompileResult, Diagnostic, Source, check_syntax, compile, constant_module,
        render_diagnostic,
    };

    #[pymodule_export]
    #[expect(
        non_upper_case_globals,
        reason = "The Python attribute is named __version__"
    )]
    const __version__: &str = env!("CARGO_PKG_VERSION");

    #[pymodule_init]
    fn initialize(module: &Bound<'_, PyModule>) -> PyResult<()> {
        module
            .py()
            .get_type::<CompileError>()
            .setattr("diagnostics", PyTuple::empty(module.py()))
    }
}
