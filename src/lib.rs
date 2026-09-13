use std::{
    borrow::Cow,
    collections::{BTreeMap, HashMap},
    path::PathBuf,
};

use pyo3::{
    create_exception,
    exceptions::{PyException, PyValueError},
    prelude::*,
    types::{PyTuple, PyType},
};
use wesl::{
    CompileOptions, Feature, Features, FileResolver, ManglerKind, ModulePath, ResolveError,
    Resolver, SourceMap, SyntaxUtil, VirtualResolver, Wesl,
};
use wgsl_parse::{
    SyntaxNode,
    error::ErrorKind,
    syntax::{ImportStatement, PathOrigin, TranslationUnit},
};

create_exception!(
    wesl,
    CompileError,
    PyException,
    "A syntax or compilation failure. The diagnostics attribute is a tuple of Diagnostic values."
);

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

#[pyclass(frozen, eq, module = "wesl")]
#[derive(PartialEq, Eq)]
struct CompileResult {
    #[pyo3(get)]
    wgsl: String,
    modules: Vec<String>,
    entry_points: Vec<String>,
    #[pyo3(get)]
    declarations: BTreeMap<String, (String, String)>,
}

#[pymethods]
impl CompileResult {
    #[new]
    fn new(
        wgsl: String,
        modules: Vec<String>,
        entry_points: Vec<String>,
        declarations: BTreeMap<String, (String, String)>,
    ) -> Self {
        Self {
            wgsl,
            modules,
            entry_points,
            declarations,
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
                &self.declarations,
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

    fn canonical_path(&self, path: &ModulePath) -> ModulePath {
        let mut path = path.clone();
        if let PathOrigin::Package(package) = &mut path.origin
            && let Some((_, name)) = package.rsplit_once('/')
        {
            *package = name.to_owned();
        }
        path
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
    Option(String),
    Compiler(Box<Diagnostic>, String),
}

impl Failure {
    fn into_pyerr(self, py: Python<'_>) -> PyErr {
        match self {
            Self::Path(path) => PyValueError::new_err(format!(
                "invalid module path {path:?}; expected an absolute module or package name"
            )),
            Self::Option(message) => PyValueError::new_err(message),
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
    let statement: ImportStatement = format!("import {path}::item;")
        .parse()
        .map_err(|_| Failure::Path(path.to_owned()))?;
    statement
        .path
        .filter(|module| !module.origin.is_relative() && module.to_string() == path)
        .ok_or_else(|| Failure::Path(path.to_owned()))
}

#[pyfunction]
#[expect(
    clippy::too_many_arguments,
    reason = "The Python binding accepts each compiler option as an argument."
)]
#[expect(
    clippy::too_many_lines,
    reason = "Keep compiler setup and result conversion together."
)]
fn compile(
    py: Python<'_>,
    modules: HashMap<String, String>,
    root: String,
    features: HashMap<String, bool>,
    strip: bool,
    keep_root: bool,
    mangle_root: bool,
    keep: Option<Vec<String>>,
    missing_features: String,
    filenames: HashMap<String, String>,
    root_directory: Option<PathBuf>,
) -> PyResult<CompileResult> {
    py.detach(move || {
        let root = module_path(&root)?;
        let default_feature = match missing_features.as_str() {
            "disable" => Feature::Disable,
            "error" => Feature::Error,
            _ => {
                return Err(Failure::Option(
                    "missing_features must be 'disable' or 'error'".to_owned(),
                ));
            }
        };
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
        compiler.set_options(CompileOptions {
            imports: true,
            condcomp: true,
            generics: false,
            strip,
            lower: false,
            validate: true,
            lazy: strip,
            mangle_root,
            keep,
            keep_root,
            features: Features {
                default: default_feature,
                flags: features
                    .into_iter()
                    .map(|(name, enabled)| (name, enabled.into()))
                    .collect(),
            },
        });
        compiler.set_mangler(ManglerKind::Escape);
        compiler.use_sourcemap(true);
        compiler
            .compile(&root)
            .map(|result| {
                let mut modules: Vec<_> = result.modules.iter().map(ToString::to_string).collect();
                modules.sort();
                CompileResult {
                    wgsl: result.to_string(),
                    modules,
                    entry_points: result
                        .syntax
                        .entry_points()
                        .map(ToString::to_string)
                        .collect(),
                    declarations: result
                        .syntax
                        .global_declarations
                        .iter()
                        .filter_map(SyntaxNode::ident)
                        .map(|identifier| {
                            let name = identifier.to_string();
                            let (module, original) = result.sourcemap.get_decl(&name).map_or_else(
                                || (root.to_string(), name.clone()),
                                |(module, original)| (module.to_string(), original.to_owned()),
                            );
                            (name, (module, original))
                        })
                        .collect(),
                }
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

#[pyfunction]
fn validate(py: Python<'_>, source: String, filename: String) -> PyResult<()> {
    py.detach(move || {
        let module = naga::front::wgsl::parse_str(&source).map_err(|error| {
            let span = error
                .labels()
                .find_map(|(span, _)| span.to_range())
                .map(|range| (range.start, range.end));
            let rendered = error.emit_to_string_with_path(&source, &filename);
            let rendered = if span.is_none() {
                format!("{filename}: {rendered}")
            } else {
                rendered
            };
            Failure::Compiler(
                Box::new(Diagnostic {
                    message: error.message().to_owned(),
                    module: None,
                    filename: Some(filename.clone()),
                    source: Some(source.clone()),
                    span,
                }),
                rendered,
            )
        })?;
        naga::valid::Validator::new(
            naga::valid::ValidationFlags::all(),
            naga::valid::Capabilities::all(),
        )
        .validate(&module)
        .map(|_| ())
        .map_err(|error| {
            let span = error
                .spans()
                .find_map(|(span, _)| span.to_range())
                .map(|range| (range.start, range.end));
            let mut message = error.to_string();
            let mut cause = std::error::Error::source(&error);
            while let Some(error) = cause {
                message.push_str(": ");
                message.push_str(&error.to_string());
                cause = error.source();
            }
            let rendered = error.emit_to_string_with_path(&source, &filename);
            let rendered = if span.is_none() {
                format!("{filename}: {rendered}")
            } else {
                rendered
            };
            Failure::Compiler(
                Box::new(Diagnostic {
                    message,
                    module: None,
                    filename: Some(filename.clone()),
                    source: Some(source.clone()),
                    span,
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
    let error = module.py().get_type::<CompileError>();
    error.setattr("diagnostics", PyTuple::empty(module.py()))?;
    module.add("CompileError", error)?;
    module.add("__version__", env!("CARGO_PKG_VERSION"))?;
    module.add("compiler_version", env!("WESL_COMPILER_VERSION"))?;
    module.add(
        "_build_metadata",
        include_str!(concat!(env!("OUT_DIR"), "/build-metadata.json")),
    )?;
    module.add_function(wrap_pyfunction!(compile, module)?)?;
    module.add_function(wrap_pyfunction!(check_syntax, module)?)?;
    module.add_function(wrap_pyfunction!(validate, module)?)?;
    Ok(())
}
