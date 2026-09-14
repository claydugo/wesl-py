use std::{
    borrow::Cow,
    collections::{BTreeMap, HashMap},
    path::PathBuf,
};

use pyo3::{
    create_exception,
    exceptions::{PyException, PyValueError},
    prelude::*,
    types::{PyMapping, PyTuple, PyType},
};
use wesl::{
    FileResolver, ModulePath, ResolveError, Resolver, SourceMap, SyntaxUtil, VirtualResolver, Wesl,
};
use wgsl_parse::{
    error::ErrorKind,
    syntax::{ImportStatement, TranslationUnit},
};

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

#[derive(FromPyObject)]
struct CompileOptions<'py> {
    imports: bool,
    condcomp: bool,
    strip: bool,
    lower: bool,
    validate: bool,
    lazy: bool,
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
            lazy: options.lazy,
            mangle_root: options.mangle_root,
            keep: options.keep,
            keep_root: options.keep_root,
            features: wesl::Features {
                default: options.features.default.try_into()?,
                flags: options
                    .features
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
            },
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
}

impl Resolver for ModuleResolver {
    fn resolve_source<'a>(&'a self, path: &ModulePath) -> Result<Cow<'a, str>, ResolveError> {
        match (self.modules.get_module(path), &self.files) {
            (Ok(source), _) => Ok(Cow::Borrowed(source)),
            (Err(_), Some(files)) if path.origin.is_absolute() => files.resolve_source(path),
            (Err(error), _) => Err(error),
        }
    }

    fn display_name(&self, path: &ModulePath) -> Option<String> {
        if self.modules.get_module(path).is_ok() {
            self.filenames.get(path).cloned()
        } else {
            self.files.as_ref()?.display_name(path)
        }
    }
}

impl Diagnostic {
    fn position(&self, offset: usize) -> Option<(usize, usize)> {
        let prefix = self.source.as_ref()?.get(..offset)?;
        Some((
            prefix.bytes().filter(|byte| *byte == b'\n').count() + 1,
            prefix.rsplit('\n').next()?.chars().count() + 1,
        ))
    }
}

enum Failure {
    Path(String),
    Compiler(Box<Diagnostic>, String),
}

impl Failure {
    fn into_pyerr(self, py: Python<'_>) -> PyErr {
        match self {
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
    mangler: &str,
    use_sourcemap: bool,
    filenames: HashMap<String, String>,
    root_directory: Option<PathBuf>,
) -> PyResult<CompileResult> {
    let modules = modules.items()?.extract::<Vec<(String, String)>>()?;
    let options = options
        .map(wesl::CompileOptions::try_from)
        .transpose()?
        .unwrap_or_default();
    let mangler = match mangler {
        "Escape" => wesl::ManglerKind::Escape,
        "Hash" => wesl::ManglerKind::Hash,
        "Unicode" => wesl::ManglerKind::Unicode,
        "None" => wesl::ManglerKind::None,
        _ => return Err(PyValueError::new_err("invalid mangler")),
    };
    py.detach(move || {
        let root = module_path(&root)?;
        let mut resolver = ModuleResolver {
            modules: VirtualResolver::new(),
            filenames: filenames
                .into_iter()
                .map(|(path, filename)| Ok((module_path(&path)?, filename)))
                .collect::<Result<_, Failure>>()?,
            files: root_directory.map(FileResolver::new),
        };
        for (path, source) in modules {
            resolver
                .modules
                .add_module(module_path(&path)?, source.into());
        }
        let mut compiler = Wesl::new_barebones().set_custom_resolver(resolver);
        compiler.set_options(options);
        compiler.set_mangler(mangler);
        compiler.use_sourcemap(use_sourcemap);
        compiler
            .compile(&root)
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
            .map_err(|error| {
                let mut diagnostic = error.diagnostic();
                if let wesl::Error::ParseError(error) = &mut *diagnostic.error
                    && matches!(error.error, ErrorKind::UnexpectedEof { .. })
                    && let Some(source) = &diagnostic.detail.source
                {
                    error.span = (source.len()..source.len()).into();
                    diagnostic.detail.span = Some(error.span);
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
                Failure::Compiler(
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
            })
    })
    .map_err(|failure| failure.into_pyerr(py))
}

#[pyfunction]
fn check_syntax(py: Python<'_>, source: String, filename: String) -> PyResult<()> {
    py.detach(move || {
        source
            .parse::<TranslationUnit>()
            .map(|_| ())
            .map_err(|mut error| {
                if matches!(error.error, ErrorKind::UnexpectedEof { .. }) {
                    error.span = (source.len()..source.len()).into();
                }
                let range = error.span.range();
                let message = error.error.to_string();
                let mut diagnostic = wesl::Diagnostic::from(error).with_source(source);
                diagnostic.detail.display_name = Some(filename);
                let rendered = diagnostic.render_plain();
                Failure::Compiler(
                    Box::new(Diagnostic {
                        message,
                        module: None,
                        filename: diagnostic.detail.display_name,
                        source: diagnostic.detail.source,
                        span: Some((range.start, range.end)),
                    }),
                    rendered,
                )
            })
    })
    .map_err(|failure| failure.into_pyerr(py))
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<Diagnostic>()?;
    module.add_class::<CompileResult>()?;
    module.add_class::<Source>()?;
    let error = module.py().get_type::<CompileError>();
    error.setattr("diagnostics", PyTuple::empty(module.py()))?;
    module.add("CompileError", error)?;
    module.add("__version__", env!("CARGO_PKG_VERSION"))?;
    module.add("build_revision", option_env!("WESL_PY_BUILD_REVISION"))?;
    module.add("compiler_version", env!("WESL_COMPILER_VERSION"))?;
    module.add(
        "_build_metadata",
        include_str!(concat!(env!("OUT_DIR"), "/build-metadata.json")),
    )?;
    module.add_function(wrap_pyfunction!(compile, module)?)?;
    module.add_function(wrap_pyfunction!(check_syntax, module)?)?;
    Ok(())
}
