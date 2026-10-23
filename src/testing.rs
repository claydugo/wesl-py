#![expect(
    clippy::too_many_arguments,
    reason = "Python bindings accept test settings and source inputs"
)]
#![expect(
    clippy::struct_excessive_bools,
    reason = "Test options mirror the Python API and upstream compiler flags"
)]

use std::{
    collections::{HashMap, HashSet},
    sync::Arc,
};

use pyo3::{
    buffer::PyBuffer,
    exceptions::{PyNotImplementedError, PyValueError},
    prelude::*,
    types::PyTuple,
};
use wesl::{
    Resolver,
    eval::{
        Context, EvalAttrs as _, Exec as _, Instance, LiteralInstance, RefInstance,
        SyntaxUtil as _, Type, ty_eval_ty,
    },
    pass::{self, Visit},
    sourcemap::SourceMap,
};
use wesl_quote::{quote_declaration, quote_expression};
use wgsl_parse::SyntaxNode;
use wgsl_parse::syntax::{
    AccessMode, AddressSpace, AssignmentOperator, AssignmentStatement, Attribute, BinaryExpression,
    BinaryOperator, BuiltinValue, CompoundStatement, Declaration, DeclarationKind, Expression,
    FormalParameter, Function, FunctionCall, FunctionCallStatement, GlobalDeclaration, Ident,
    IfClause, IfStatement, LiteralExpression, ModulePath, NamedComponentExpression,
    ParenthesizedExpression, PathOrigin, Span, Spanned, Statement, StatementNode, Struct,
    StructMember, TemplateArg, TranslationUnit, TypeExpression, UnaryExpression, UnaryOperator,
    Visibility, WorkgroupSizeAttribute,
};

use crate::{Compiler, Diagnostic, Failure, Features, ModuleResolver, module_path};

fn available_name(mut name: String, mut is_used: impl FnMut(&str) -> bool) -> String {
    while is_used(&name) {
        name.push('_');
    }
    name
}

fn global_declarations(
    syntax: &TranslationUnit,
) -> impl Iterator<Item = &Spanned<GlobalDeclaration>> {
    let mut pending: Vec<_> = syntax.global_declarations.iter().collect();
    std::iter::from_fn(move || {
        let declaration = pending.pop()?;
        if let GlobalDeclaration::Compound(compound) = &**declaration {
            pending.extend(&compound.body);
        }
        Some(declaration)
    })
}

#[derive(Clone, IntoPyObject)]
pub(super) struct Buffer {
    name: String,
    binding: u32,
    size: u32,
    layout: Option<Layout>,
    access: &'static str,
}

type Placement = (Vec<(bool, Buffer)>, Vec<(u32, u32)>);

#[derive(Clone)]
pub(super) enum Layout {
    Scalar(&'static str),
    Array(Box<Self>, Option<usize>, u32),
    Struct(Vec<(String, u32, Self)>, u32),
}

impl<'py> IntoPyObject<'py> for Layout {
    type Target = PyAny;
    type Output = Bound<'py, PyAny>;
    type Error = PyErr;

    fn into_pyobject(self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        match self {
            Self::Scalar(name) => Ok(name.into_pyobject(py)?.into_any()),
            Self::Array(element, count, stride) => Ok(("array", *element, count, stride)
                .into_pyobject(py)?
                .into_any()),
            Self::Struct(members, size) => {
                Ok(("struct", members, size).into_pyobject(py)?.into_any())
            }
        }
    }
}

fn layout(value_type: &Type) -> Option<Layout> {
    match value_type {
        Type::F32 => Some(Layout::Scalar("f32")),
        Type::I32 => Some(Layout::Scalar("i32")),
        Type::U32 => Some(Layout::Scalar("u32")),
        Type::F16 => Some(Layout::Scalar("f16")),
        Type::Atomic(inner) => layout(inner),
        Type::Vec(components, inner) => Some(Layout::Array(
            Box::new(layout(inner)?),
            Some(usize::from(*components)),
            inner.size_of()?,
        )),
        Type::Mat(columns, rows, inner) => {
            let column = Type::Vec(*rows, inner.clone());
            Some(Layout::Array(
                Box::new(layout(&column)?),
                Some(usize::from(*columns)),
                column.align_of()?,
            ))
        }
        Type::Array(element, count) => Some(Layout::Array(
            Box::new(layout(element)?),
            *count,
            element.size_of()?.next_multiple_of(element.align_of()?),
        )),
        Type::Struct(structure) => {
            let mut members = Vec::new();
            let mut end = 0u32;
            for member in &structure.members {
                let size = member.size.or_else(|| member.ty.size_of())?;
                let offset = end.next_multiple_of(member.align.or_else(|| member.ty.align_of())?);
                members.push((member.name.clone(), offset, layout(&member.ty)?));
                end = offset + size;
            }
            Some(Layout::Struct(members, value_type.size_of()?))
        }
        _ => None,
    }
}

fn constant_context(syntax: &TranslationUnit) -> Context<'_> {
    let mut context = Context::new(syntax);
    let mut constants: Vec<_> = syntax
        .global_declarations
        .iter()
        .filter_map(|declaration| match &**declaration {
            GlobalDeclaration::Declaration(value) if value.kind == DeclarationKind::Const => {
                Some(value)
            }
            _ => None,
        })
        .collect();
    loop {
        let count = constants.len();
        constants.retain(|value| value.exec(&mut context).is_err());
        if constants.len() == count {
            break;
        }
    }
    context
}

#[expect(
    clippy::too_many_lines,
    reason = "Buffer placement finds reached declarations, validates @buffer variables, and assigns bindings"
)]
fn place_buffers(
    syntax: &mut TranslationUnit,
    sourcemap: &impl SourceMap,
    root: &ModulePath,
    entry_point: &str,
    reserved: &[u32],
) -> Result<Placement, Failure> {
    let declarations: HashMap<String, &GlobalDeclaration> = syntax
        .global_declarations
        .iter()
        .filter_map(|declaration| Some((declaration.ident()?.name().clone(), &**declaration)))
        .collect();
    let mut reached = HashSet::from([entry_point.to_owned()]);
    let mut pending: Vec<_> = declarations.get(entry_point).into_iter().copied().collect();
    while let Some(current) = pending.pop() {
        Visit::<TypeExpression>::visit_rec(current, &mut |expression: &TypeExpression| {
            let name = expression.ident.name();
            if let Some(&declaration) = declarations.get(&*name)
                && reached.insert(name.clone())
            {
                pending.push(declaration);
            }
        });
    }
    let mut taken: HashSet<u32> = reserved.iter().copied().collect();
    let mut resources = Vec::new();
    let mut found = Vec::new();
    let mut context = constant_context(syntax);
    for (index, declaration) in syntax.global_declarations.iter().enumerate() {
        let GlobalDeclaration::Declaration(value) = &**declaration else {
            continue;
        };
        let bound = value
            .attributes
            .iter()
            .any(|attribute| matches!(&**attribute, Attribute::Group(_) | Attribute::Binding(_)));
        let name = value
            .attributes
            .iter()
            .any(|attribute| matches!(&**attribute, Attribute::Custom(custom) if custom.name == "buffer"))
            .then(|| {
                sourcemap.item(&value.ident.name()).map_or_else(
                    || Some(value.ident.name().clone()),
                    |entry| (entry.path == *root).then(|| entry.name.clone()),
                )
            })
            .flatten();
        let Some(name) = name else {
            if bound && let Ok((group, number)) = value.attr_group_binding(&mut context) {
                if group == 0 {
                    taken.insert(number);
                }
                if reached.contains(&*value.ident.name()) {
                    resources.push((group, number));
                }
            }
            continue;
        };
        let DeclarationKind::Var(Some((AddressSpace::Storage, access))) = &value.kind else {
            return Err(Failure::Message(format!(
                "@buffer variable {name} must be a var<storage>"
            )));
        };
        if bound {
            return Err(Failure::Message(format!(
                "@buffer variable {name} takes its binding from the test runner"
            )));
        }
        let Some(value_type) = &value.ty else {
            continue;
        };
        let value_type = resolve_assertion_type(value_type, &mut context)
            .map_err(|error| Failure::from_diagnostic(error.into()))?;
        found.push((
            index,
            reached.contains(&*value.ident.name()),
            Buffer {
                name,
                binding: 0,
                size: value_type.size_of().unwrap_or(0).max(4),
                layout: layout(&value_type),
                access: if matches!(access, Some(AccessMode::ReadWrite)) {
                    "read_write"
                } else {
                    "read"
                },
            },
        ));
    }
    let mut next = 0;
    let mut buffers = Vec::new();
    for (index, reached, mut buffer) in found {
        while taken.contains(&next) {
            next += 1;
        }
        taken.insert(next);
        if let GlobalDeclaration::Declaration(value) = &mut *syntax.global_declarations[index] {
            value.attributes.retain(|attribute| {
                !matches!(&**attribute, Attribute::Custom(custom) if custom.name == "buffer")
            });
            value
                .attributes
                .push(Attribute::Group(Expression::from(0u32).into()).into());
            value
                .attributes
                .push(Attribute::Binding(Expression::from(next).into()).into());
        }
        buffer.binding = next;
        buffers.push((reached, buffer));
    }
    Ok((buffers, resources))
}

type CompiledCompute = (String, Vec<Buffer>, HashMap<String, String>);

#[pyo3_stub_gen::derive::gen_stub_pyfunction(module = "wesl._native")]
#[pyfunction]
#[pyo3(signature = (compiler, root))]
#[gen_stub(override_return_type(
    type_repr = "tuple[str, list[dict[str, typing.Any]], dict[str, str]]",
    imports = ("typing")
))]
pub(super) fn compile_compute(
    py: Python<'_>,
    #[gen_stub(override_type(type_repr="wesl.Compiler", imports=("wesl")))] compiler: Compiler<'_>,
    root: String,
) -> PyResult<CompiledCompute> {
    let (options, sources) = compiler.split()?;
    py.detach(move || {
        let root = module_path(&root)?;
        let resolver = ModuleResolver::new(sources)?;
        let mut result = crate::compiler::compile(
            &root,
            &wesl::CompileOptions {
                visibility: false,
                keep_main: true,
                features: options.features,
                ..Default::default()
            },
            &resolver,
            HashMap::new(),
            |_, _| Ok(()),
        )
        .map_err(|error| Failure::from_diagnostic(error.diagnostic()))?;
        let (buffers, _) =
            place_buffers(&mut result.syntax, &result.sourcemap, &root, "main", &[])?;
        Ok((
            result.syntax.to_string(),
            buffers.into_iter().map(|(_, buffer)| buffer).collect(),
            source_names(&result.syntax, &result.sourcemap),
        ))
    })
    .map_err(|failure: Failure| failure.into_pyerr(py))
}

fn references_override<N: Visit<TypeExpression>>(syntax: &TranslationUnit, node: &N) -> bool {
    let mut names = Vec::new();
    node.visit_rec(&mut |expression: &TypeExpression| {
        names.push(expression.ident.name().to_string());
    });
    let mut checked = HashSet::new();
    while let Some(name) = names.pop() {
        if !checked.insert(name.clone()) {
            continue;
        }
        match syntax.user_decl(&name) {
            Some(GlobalDeclaration::Declaration(value))
                if value.kind == DeclarationKind::Override =>
            {
                return true;
            }
            Some(declaration) => declaration.visit_rec(&mut |expression: &TypeExpression| {
                names.push(expression.ident.name().to_string());
            }),
            None => {}
        }
    }
    false
}

fn compile_module(
    resolver: &ModuleResolver,
    module: &str,
    features: wesl::Features,
) -> Result<(ModulePath, wesl::CompileResult), Failure> {
    let root = module_path(module)?;
    let result = crate::compiler::compile(
        &root,
        &wesl::CompileOptions {
            visibility: false,
            strip: false,
            validate: false,
            features,
            ..Default::default()
        },
        resolver,
        HashMap::new(),
        |_, _| Ok(()),
    )
    .map_err(|error| Failure::from_diagnostic(error.diagnostic()))?;
    Ok((root, result))
}

fn module_failure(error: impl Into<wesl::Error>, root: &ModulePath) -> Failure {
    Failure::from_diagnostic(
        error
            .into()
            .diagnostic()
            .with_module_path(root.clone(), None),
    )
}

fn module_items<'a>(
    root: &'a ModulePath,
    result: &'a wesl::CompileResult,
) -> impl Iterator<Item = (String, &'a GlobalDeclaration)> {
    result
        .syntax
        .global_declarations
        .iter()
        .filter_map(move |declaration| {
            let ident = declaration.ident()?.name().to_string();
            match result.sourcemap.item(&ident) {
                None => Some((ident, &**declaration)),
                Some(entry) if entry.path == *root => Some((entry.name.clone(), &**declaration)),
                Some(_) => None,
            }
        })
}

#[pyo3_stub_gen::derive::gen_stub_pyfunction(module = "wesl._native")]
#[pyfunction]
#[pyo3(signature = (compiler, path))]
#[gen_stub(override_return_type(
    type_repr = "builtins.tuple[builtins.bool, builtins.str | builtins.tuple[typing.Any, ...]]",
    imports = ("builtins", "typing")
))]
pub(super) fn path_layout(
    py: Python<'_>,
    #[gen_stub(override_type(type_repr="wesl.Compiler", imports=("wesl")))] compiler: Compiler<'_>,
    path: String,
) -> PyResult<(bool, Layout)> {
    let (options, sources) = compiler.split()?;
    py.detach(move || {
        let Some((module, name)) = path.rsplit_once("::") else {
            return Err(Failure::Shape(
                format!("{path:?} does not name a module and an item"),
                None,
            ));
        };
        let resolver = ModuleResolver::new(sources)?;
        let (root, result) = compile_module(&resolver, module, options.features)?;
        let (variable, type_expression) = match module_items(&root, &result)
            .find_map(|(item, declaration)| (item == name).then_some(declaration))
        {
            Some(GlobalDeclaration::Declaration(Declaration {
                kind: DeclarationKind::Var(_),
                ty: Some(value_type),
                ..
            })) => (true, value_type.clone()),
            Some(
                declaration @ (GlobalDeclaration::Struct(_) | GlobalDeclaration::TypeAlias(_)),
            ) => (
                false,
                TypeExpression::from(
                    declaration
                        .ident()
                        .unwrap_or_else(|| Ident::new(name.to_owned())),
                ),
            ),
            _ => {
                return Err(Failure::Shape(
                    format!("{path} does not name a type or a typed module-scope var"),
                    Some(name.to_owned()),
                ));
            }
        };
        let mut context = constant_context(&result.syntax);
        let value_type = (!references_override(&result.syntax, &type_expression))
            .then(|| resolve_assertion_type(&type_expression, &mut context))
            .transpose()
            .map_err(|error| module_failure(error, &root))?;
        value_type
            .and_then(|value_type| {
                layout(&if variable {
                    value_type
                } else {
                    Type::Array(Box::new(value_type), None)
                })
            })
            .map(|layout| (variable, layout))
            .ok_or_else(|| {
                Failure::Shape(
                    format!("{path} has no fixed-size host-shareable layout"),
                    Some(name.to_owned()),
                )
            })
    })
    .map_err(|failure: Failure| failure.into_pyerr(py))
}

type VarReflection = (
    Option<String>,
    Option<String>,
    Option<u32>,
    Option<u32>,
    Option<Layout>,
    u32,
);

#[pyo3_stub_gen::derive::gen_stub_pyfunction(module = "wesl._native")]
#[pyfunction]
#[pyo3(signature = (compiler, path))]
#[gen_stub(override_return_type(
    type_repr = "builtins.tuple[builtins.str | None, builtins.str | None, builtins.int | None, builtins.int | None, builtins.str | builtins.tuple[typing.Any, ...] | None, builtins.int]",
    imports = ("builtins", "typing")
))]
pub(super) fn var_reflection(
    py: Python<'_>,
    #[gen_stub(override_type(type_repr="wesl.Compiler", imports=("wesl")))] compiler: Compiler<'_>,
    path: String,
) -> PyResult<VarReflection> {
    let (options, sources) = compiler.split()?;
    py.detach(move || {
        let Some((module, name)) = path.rsplit_once("::") else {
            return Err(Failure::Shape(
                format!("{path:?} does not name a module and a variable"),
                None,
            ));
        };
        let resolver = ModuleResolver::new(sources)?;
        let (root, result) = compile_module(&resolver, module, options.features)?;
        let Some((declaration, space, value_type)) =
            module_items(&root, &result).find_map(|(item, declaration)| match declaration {
                GlobalDeclaration::Declaration(
                    value @ Declaration {
                        kind: DeclarationKind::Var(space),
                        ty: Some(value_type),
                        ..
                    },
                ) if item == name => Some((value, space, value_type)),
                _ => None,
            })
        else {
            return Err(Failure::Shape(
                format!("{path} does not name a typed module-scope var"),
                Some(name.to_owned()),
            ));
        };
        let mut context = constant_context(&result.syntax);
        let value_type = (!references_override(&result.syntax, value_type))
            .then(|| resolve_assertion_type(value_type, &mut context))
            .transpose()
            .map_err(|error| module_failure(error, &root))?;
        if matches!(value_type, Some(Type::Texture(_) | Type::Sampler(_))) {
            return Err(Failure::Shape(
                format!("{path} is a texture or sampler"),
                Some(name.to_owned()),
            ));
        }
        let (group, binding) = declaration
            .attributes
            .iter()
            .any(|attribute| matches!(&**attribute, Attribute::Group(_) | Attribute::Binding(_)))
            .then(|| declaration.attr_group_binding(&mut context))
            .transpose()
            .map_err(|error| module_failure(error, &root))?
            .unzip();
        Ok((
            space.as_ref().map(|(space, _)| space.to_string()),
            space
                .as_ref()
                .and_then(|(_, access)| access.as_ref().map(ToString::to_string)),
            group,
            binding,
            value_type.as_ref().and_then(layout),
            value_type.as_ref().and_then(Type::size_of).unwrap_or(0),
        ))
    })
    .map_err(|failure: Failure| failure.into_pyerr(py))
}

#[pyo3_stub_gen::derive::gen_stub_pyfunction(module = "wesl._native")]
#[pyfunction]
#[pyo3(signature = (compiler, module))]
#[gen_stub(override_return_type(
    type_repr = "builtins.list[builtins.tuple[builtins.str, builtins.str | builtins.tuple[typing.Any, ...] | None]]",
    imports = ("builtins", "typing")
))]
pub(super) fn struct_layouts(
    py: Python<'_>,
    #[gen_stub(override_type(type_repr="wesl.Compiler", imports=("wesl")))] compiler: Compiler<'_>,
    module: String,
) -> PyResult<Vec<(String, Option<Layout>)>> {
    let (options, sources) = compiler.split()?;
    py.detach(move || {
        let resolver = ModuleResolver::new(sources)?;
        let (root, result) = compile_module(&resolver, &module, options.features)?;
        let mut context = Context::new(&result.syntax);
        module_items(&root, &result)
            .filter_map(|(item, declaration)| match declaration {
                GlobalDeclaration::Struct(structure) => Some((item, structure)),
                _ => None,
            })
            .map(|(item, structure)| {
                let value_type = resolve_assertion_type(
                    &TypeExpression::from(structure.ident.clone()),
                    &mut context,
                )
                .map_err(|error| module_failure(error, &root))?;
                Ok((item, layout(&value_type)))
            })
            .collect::<Result<Vec<_>, Failure>>()
    })
    .map_err(|failure: Failure| failure.into_pyerr(py))
}

type EntryPoint = (String, &'static str, Option<(u32, u32, u32)>);

#[pyo3_stub_gen::derive::gen_stub_pyfunction(module = "wesl._native")]
#[pyfunction]
#[pyo3(signature = (compiler, module))]
pub(super) fn entry_points(
    py: Python<'_>,
    #[gen_stub(override_type(type_repr="wesl.Compiler", imports=("wesl")))] compiler: Compiler<'_>,
    module: String,
) -> PyResult<Vec<EntryPoint>> {
    let (options, sources) = compiler.split()?;
    py.detach(move || {
        let resolver = ModuleResolver::new(sources)?;
        let (root, result) = compile_module(&resolver, &module, options.features)?;
        let mut context = constant_context(&result.syntax);
        let mut entry_points = Vec::new();
        for (item, declaration) in module_items(&root, &result) {
            let GlobalDeclaration::Function(function) = declaration else {
                continue;
            };
            let Some(stage) = function
                .attributes
                .iter()
                .find_map(|attribute| match &**attribute {
                    Attribute::Compute => Some("compute"),
                    Attribute::Fragment => Some("fragment"),
                    Attribute::Vertex => Some("vertex"),
                    _ => None,
                })
            else {
                continue;
            };
            let workgroup_size = match function
                .attributes
                .iter()
                .find(|attribute| matches!(&***attribute, Attribute::WorkgroupSize(_)))
            {
                Some(attribute) if !references_override(&result.syntax, &**attribute) => {
                    let (x, y, z) = function
                        .attr_workgroup_size(&mut context)
                        .map_err(|error| module_failure(error, &root))?;
                    Some((x, y.unwrap_or(1), z.unwrap_or(1)))
                }
                _ => None,
            };
            entry_points.push((item, stage, workgroup_size));
        }
        Ok(entry_points)
    })
    .map_err(|failure: Failure| failure.into_pyerr(py))
}

#[pyo3_stub_gen::derive::gen_stub_pyclass(module = "wesl._native")]
#[pyclass(frozen, module = "wesl._native")]
pub(super) struct TestLayout {
    result_type: Type,
    #[pyo3(get)]
    buffer_size: u32,
    cooperative: bool,
    buffers: Vec<Buffer>,
    #[pyo3(get)]
    resources: Vec<(u32, u32)>,
}

#[pyo3_stub_gen::derive::gen_stub_pymethods]
#[pymethods]
impl TestLayout {
    #[getter]
    #[gen_stub(override_return_type(
        type_repr = "list[dict[str, typing.Any]]",
        imports = ("typing")
    ))]
    fn buffers<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyAny>> {
        self.buffers.clone().into_pyobject(py).map(Bound::into_any)
    }

    #[pyo3(signature = (data))]
    fn decode(
        &self,
        #[gen_stub(override_type(type_repr="collections.abc.Buffer", imports=("collections.abc")))]
        data: &Bound<'_, PyAny>,
    ) -> PyResult<TestResult> {
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

#[pyo3_stub_gen::derive::gen_stub_pyclass(module = "wesl._native")]
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

#[pyo3_stub_gen::derive::gen_stub_pymethods]
#[pymethods]
impl TestResult {
    #[getter]
    #[gen_stub(override_return_type(
        type_repr = "tuple[bool | int | float | tuple[bool | int | float, ...], bool | int | float | tuple[bool | int | float, ...]]"
    ))]
    fn values<'py>(&self, py: Python<'py>) -> PyResult<(Bound<'py, PyAny>, Bound<'py, PyAny>)> {
        let [actual, expected] = [&self.actual, &self.expected].map(|value| -> PyResult<_> {
            let components = usize::try_from(self.components)
                .map_err(|error| PyValueError::new_err(error.to_string()))?;
            let values = value
                .get(..components)
                .ok_or_else(|| PyValueError::new_err("shader assertion has too many components"))?
                .iter()
                .map(|&bits| -> PyResult<Bound<'py, PyAny>> {
                    match self.value_kind {
                        0 => Ok((bits != 0).into_pyobject(py)?.to_owned().into_any()),
                        1 => Ok(bits.into_pyobject(py)?.into_any()),
                        3 => Ok(bits.cast_signed().into_pyobject(py)?.into_any()),
                        _ => Ok(f32::from_bits(bits).into_pyobject(py)?.into_any()),
                    }
                })
                .collect::<PyResult<Vec<_>>>()?;
            if components == 1 {
                Ok(values
                    .into_iter()
                    .next()
                    .ok_or_else(|| PyValueError::new_err("shader assertion has no components"))?)
            } else {
                Ok(PyTuple::new(py, values)?.into_any())
            }
        });
        Ok((actual?, expected?))
    }

    #[getter]
    const fn value_type(&self) -> &'static str {
        match (self.value_kind, self.components) {
            (0, _) => "bool",
            (1, 1) => "u32",
            (1, 2) => "vec2u",
            (1, 3) => "vec3u",
            (1, _) => "vec4u",
            (3, 1) => "i32",
            (3, 2) => "vec2i",
            (3, 3) => "vec3i",
            (3, _) => "vec4i",
            (_, 1) => "f32",
            (_, 2) => "vec2f",
            (_, 3) => "vec3f",
            _ => "vec4f",
        }
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

struct PreparedTest {
    transformed: TestTransform,
    parsed_modules: HashMap<ModulePath, TranslationUnit>,
    syntax: TranslationUnit,
}

struct TestTransform {
    root: ModulePath,
    test_name: String,
    entry_point: String,
    assertion_module: ModulePath,
    result_module: ModulePath,
    result_binding: u32,
    reserved: Vec<u32>,
    parameters: Vec<FormalParameter>,
    workgroup_size: Option<WorkgroupSizeAttribute>,
    cooperative: bool,
    collector: Ident,
    names: Vec<String>,
}

impl TestTransform {
    fn prepare(
        root: ModulePath,
        test_name: String,
        result_binding: u32,
        reserved: Vec<u32>,
        features: &wesl::Features,
        resolver: &ModuleResolver,
        syntax: Option<TranslationUnit>,
    ) -> Result<Option<PreparedTest>, Failure> {
        let mut syntax = syntax
            .map_or_else(|| crate::compiler::load_module(&root, &resolver), Ok)
            .map_err(|error| Failure::from_diagnostic(wesl::error::Diagnostic::from(error)))?;
        let mut names = test_names(&syntax, &root, &test_name)?;
        let entry_point = available_name("wesl_test_entry".to_owned(), |name| {
            names.iter().any(|used| used == name)
        });
        let root_syntax = syntax.clone();
        let Some(function) = test_function(&mut syntax, &root, &test_name, features, resolver)?
        else {
            return Ok(None);
        };
        let parameters = function.parameters.clone();
        let workgroup_size = function.attributes.iter().find_map(|attribute| {
            if let Attribute::WorkgroupSize(size) = &**attribute {
                Some(size.clone())
            } else {
                None
            }
        });
        let assertion_module = module_path("wgsl_test")?;
        let result_module = module_path("wgsl_test::TestResult")?;
        let cooperative = !parameters.is_empty() || workgroup_size.is_some();
        let result_syntax = crate::compiler::load_module(&result_module, &resolver)
            .map_err(|error| Failure::from_diagnostic(wesl::error::Diagnostic::from(error)))?;
        for declaration in global_declarations(&result_syntax) {
            if let Some(ident) = declaration.ident() {
                names.push(ident.name().to_string());
            }
        }
        let collector = available_name("wesl_test_collect".to_owned(), |collector| {
            [
                collector.to_owned(),
                format!("{collector}_output"),
                format!("{collector}_result"),
            ]
            .iter()
            .any(|name| names.contains(name))
        });
        let transformed = Self {
            root: root.clone(),
            test_name,
            entry_point,
            assertion_module,
            result_module: result_module.clone(),
            result_binding,
            reserved,
            parameters,
            workgroup_size,
            cooperative,
            collector: Ident::new(collector),
            names,
        };
        Ok(Some(PreparedTest {
            transformed,
            parsed_modules: HashMap::from([(root, root_syntax), (result_module, result_syntax)]),
            syntax,
        }))
    }

    fn compile(
        &self,
        options: &wesl::CompileOptions,
        resolver: &ModuleResolver,
        parsed_modules: HashMap<ModulePath, TranslationUnit>,
    ) -> Result<CompiledTest, Failure> {
        let mut result = crate::compiler::compile(
            &self.root,
            options,
            resolver,
            parsed_modules,
            |path, syntax| self.apply(path, syntax),
        )
        .map_err(|error| Failure::from_diagnostic(error.diagnostic()))?;
        let sourcemap = result.sourcemap.take();
        TestInstrumentation::new(&result.syntax, &sourcemap, self)?.finish(result, &sourcemap, self)
    }

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
            self.transform_result_module(syntax);
        }
        if path != &self.root {
            return Ok(());
        }
        let wrapper = self.entry_point_wrapper();
        strip_test_attributes(syntax);
        syntax.global_declarations.push(wrapper.into());
        Ok(())
    }

    fn transform_result_module(&self, syntax: &mut TranslationUnit) {
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
                    structure = self.extend_result_structure(result_structure);
                }
                _ => {}
            }
        }
        if let (Some(structure), Some(binding)) = (structure, binding) {
            self.add_collector(syntax, structure, binding);
        }
    }

    fn extend_result_structure(&self, result_structure: &mut Struct) -> Option<Struct> {
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
            return Some(result_structure.clone());
        }
        None
    }

    fn add_collector(
        &self,
        syntax: &mut TranslationUnit,
        mut structure: Struct,
        mut binding: Declaration,
    ) {
        let output = Ident::new(format!("{}_output", self.collector));
        structure.ident = Ident::new(format!("{}_result", self.collector));
        for member in &mut structure.members {
            if matches!(
                member.ident.name().as_str(),
                "passed" | "failCount" | "checks" | "completed"
            ) && let Expression::TypeOrIdentifier(member_type) = quote_expression!(atomic<u32>)
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

    fn entry_point_wrapper(&self) -> GlobalDeclaration {
        let test_name = &self.test_name;
        let mut wrapper = quote_declaration! {
            @compute @workgroup_size(1) fn wesl_test_entry() {
                wgsl_test::TestResult::initTestResult();
                #test_name();
                wgsl_test::TestResult::testResult.completed = 1u;
            }
        };
        if let GlobalDeclaration::Function(function) = &mut wrapper {
            self.configure_entry_point(function);
            if self.cooperative {
                self.add_cooperative_collection(function);
            }
        }
        wrapper
    }

    fn configure_entry_point(&self, function: &mut Function) {
        function.ident = Ident::new(self.entry_point.clone());
        function.parameters.clone_from(&self.parameters);
        for (index, parameter) in function.parameters.iter_mut().enumerate() {
            let name = available_name(format!("{}_parameter_{index}", self.entry_point), |name| {
                self.names.iter().any(|used| used == name)
            });
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
    }

    fn invocation_parameter(&self, function: &mut Function) -> Ident {
        if let Some(parameter) = function.parameters.iter().find(|parameter| {
            parameter.attributes.iter().any(|attribute| {
                matches!(
                    &**attribute,
                    Attribute::Builtin(BuiltinValue::LocalInvocationIndex)
                )
            })
        }) {
            parameter.ident.clone()
        } else {
            let name = available_name(format!("{}_invocation", self.entry_point), |name| {
                self.names.iter().any(|used| used == name)
                    || function
                        .parameters
                        .iter()
                        .any(|parameter| parameter.ident.name().as_str() == name)
            });
            let identifier = Ident::new(name);
            function.parameters.push(FormalParameter {
                attributes: vec![Attribute::Builtin(BuiltinValue::LocalInvocationIndex).into()],
                ident: identifier.clone(),
                ty: Ident::new("u32".to_owned()).into(),
            });
            identifier
        }
    }

    fn add_cooperative_collection(&self, function: &mut Function) {
        let invocation = self.invocation_parameter(function);
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

fn test_names(
    syntax: &TranslationUnit,
    root: &ModulePath,
    test_name: &str,
) -> Result<Vec<String>, Failure> {
    let mut names = Vec::new();
    let mut test_exists = false;
    for declaration in global_declarations(syntax) {
        if let Some(ident) = declaration.ident() {
            names.push(ident.name().to_string());
        }
        if let GlobalDeclaration::Function(function) = &**declaration
            && function.ident.name().as_str() == test_name
            && function.attributes.iter().any(|attribute| {
                matches!(&**attribute, Attribute::Custom(custom) if custom.name == "test")
            })
        {
            test_exists = true;
        }
    }
    if !test_exists {
        return Err(Failure::Message(format!(
            "shader test {test_name:?} does not exist"
        )));
    }
    names.extend(
        pass::flatten_imports(&syntax.imports, root)
            .into_keys()
            .map(|ident| ident.to_string()),
    );
    Ok(names)
}

fn test_function<'a>(
    syntax: &'a mut TranslationUnit,
    root: &ModulePath,
    test_name: &str,
    features: &wesl::Features,
    resolver: &ModuleResolver,
) -> Result<Option<&'a Function>, Failure> {
    if let Err(error) = pass::condcomp(syntax, features) {
        return Err(Failure::from_diagnostic(
            error
                .diagnostic()
                .with_source(
                    resolver
                        .resolve_source(root)
                        .map_err(|error| {
                            Failure::from_diagnostic(wesl::error::Diagnostic::from(error))
                        })?
                        .into_owned(),
                )
                .with_module_path(root.clone(), resolver.display_name(root)),
        ));
    }
    let Some(declaration) = syntax.global_declarations.iter().find(|declaration| {
        matches!(&***declaration, GlobalDeclaration::Function(function)
        if function.ident.name().as_str() == test_name
            && function.attributes.iter().any(|attribute| {
                matches!(&**attribute, Attribute::Custom(custom) if custom.name == "test")
            }))
    }) else {
        return Ok(None);
    };
    if let GlobalDeclaration::Function(function) = &**declaration
        && (function.parameters.iter().any(|parameter| {
            !parameter
                .attributes
                .iter()
                .any(|attribute| matches!(&**attribute, Attribute::Builtin(_)))
        }) || function.return_type.is_some()
            || function
                .attributes
                .iter()
                .any(|attribute| attribute.is_entry_point()))
    {
        return Err(Failure::from_diagnostic(wesl::Error::Custom(
            "@test requires a function with only builtin parameters, no return value, and no shader stage".to_owned(),
        ).diagnostic().with_source(
            resolver.resolve_source(root)
                .map_err(|error| Failure::from_diagnostic(wesl::error::Diagnostic::from(error)))?
                .into_owned(),
        ).with_module_path(root.clone(), resolver.display_name(root))
        .with_span(declaration.span())));
    }
    match &**declaration {
        GlobalDeclaration::Function(function) => Ok(Some(function)),
        _ => Err(Failure::Message("shader test is not a function".to_owned())),
    }
}

fn strip_test_attributes(syntax: &mut TranslationUnit) {
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
}

#[pyo3_stub_gen::derive::gen_stub_pyclass(module = "wesl._native")]
#[pyclass(frozen, module = "wesl._native")]
pub(super) struct ParsedTestModule {
    source: String,
    syntax: TranslationUnit,
    #[pyo3(get)]
    tests: Vec<(String, usize, usize)>,
}

#[pyo3_stub_gen::derive::gen_stub_pymethods]
#[pymethods]
impl ParsedTestModule {
    #[new]
    fn new(py: Python<'_>, source: String, filename: String) -> PyResult<Self> {
        py.detach(move || {
            let syntax = source
                .parse::<TranslationUnit>()
                .map_err(wesl::error::Diagnostic::from)
                .map_err(|mut diagnostic| {
                    diagnostic.detail.source = Some(source.clone());
                    diagnostic.detail.display_name = Some(filename);
                    Failure::from_diagnostic(diagnostic)
                })?;
            let mut tests = Vec::new();
            for declaration in global_declarations(&syntax) {
                if let GlobalDeclaration::Function(function) = &**declaration
                    && function.attributes.iter().any(|attribute| {
                        matches!(&**attribute, Attribute::Custom(custom) if custom.name == "test")
                    })
                {
                    let range = declaration.span().range();
                    tests.push((function.ident.name().to_string(), range.start, range.end));
                }
            }
            tests.sort_by_key(|test| test.1);
            Ok(Self {
                source,
                syntax,
                tests,
            })
        })
        .map_err(|failure: Failure| failure.into_pyerr(py))
    }
}

type CompiledTest = Option<(
    String,
    String,
    Vec<Diagnostic>,
    HashMap<String, String>,
    TestLayout,
)>;

fn source_names(syntax: &TranslationUnit, sourcemap: &impl SourceMap) -> HashMap<String, String> {
    syntax
        .global_declarations
        .iter()
        .filter_map(|declaration| {
            let ident = declaration.ident()?.name().to_string();
            let entry = sourcemap
                .item(&ident)
                .or_else(|| sourcemap.item(ident.strip_suffix("_wesl_test")?))?;
            (entry.name != ident).then(|| (ident, format!("{}::{}", entry.path, entry.name)))
        })
        .collect()
}

#[derive(Default)]
struct TestInstrumentation {
    assertions: HashMap<String, (String, Option<Type>)>,
    result_name: Option<String>,
    result_type: Option<Type>,
    compiled_entry: Option<String>,
    sites: Vec<Diagnostic>,
    sources: HashMap<ModulePath, Option<Arc<str>>>,
    referenced_assertions: HashSet<String>,
}

impl TestInstrumentation {
    fn new(
        syntax: &TranslationUnit,
        sourcemap: &impl SourceMap,
        transformed: &TestTransform,
    ) -> Result<Self, Failure> {
        let mut instrumentation = Self::default();
        let Self {
            assertions,
            result_name,
            result_type,
            compiled_entry,
            ..
        } = &mut instrumentation;
        let mut context = Context::new(syntax);
        for declaration in &syntax.global_declarations {
            if let Some(ident) = declaration.ident()
                && let Some(wesl::sourcemap::SourceMapEntry {
                    path: module, name, ..
                }) = sourcemap.item(&ident.name())
            {
                let value_type = match &**declaration {
                    GlobalDeclaration::Function(function)
                        if module == &transformed.assertion_module
                            && name.starts_with("expect") =>
                    {
                        function.parameters.first().map(|parameter| &parameter.ty)
                    }
                    GlobalDeclaration::Declaration(value)
                        if module == &transformed.result_module && name == "testResult" =>
                    {
                        value.ty.as_ref()
                    }
                    _ => None,
                };
                let value_type = assertion_type(
                    value_type,
                    module,
                    declaration.span(),
                    sourcemap,
                    &mut context,
                )?;
                if module == &transformed.assertion_module
                    && name.starts_with("expect")
                    && matches!(&**declaration, GlobalDeclaration::Function(_))
                {
                    assertions.insert(ident.name().to_string(), (name.to_owned(), value_type));
                } else if module == &transformed.result_module && name == "testResult" {
                    *result_name = Some(ident.name().to_string());
                    *result_type = value_type;
                } else if module == &transformed.root && *name == transformed.entry_point {
                    *compiled_entry = Some(ident.name().to_string());
                }
            }
        }
        Ok(instrumentation)
    }

    fn rewrite_calls(
        &mut self,
        syntax: &mut TranslationUnit,
        sourcemap: &impl SourceMap,
        transformed: &TestTransform,
    ) -> Result<(), Failure> {
        let Self {
            assertions,
            sites,
            sources,
            referenced_assertions,
            ..
        } = self;
        for declaration in &mut syntax.global_declarations {
            let GlobalDeclaration::Function(function) = &mut **declaration else {
                continue;
            };
            let Some(wesl::sourcemap::SourceMapEntry { path: module, .. }) =
                sourcemap.item(&function.ident.name())
            else {
                continue;
            };
            if module == &transformed.assertion_module || module == &transformed.result_module {
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
                            source: sources
                                .entry(module.clone())
                                .or_insert_with(|| sourcemap.source(module).map(Arc::<str>::from))
                                .as_ref()
                                .map(Arc::clone),
                            span: Some((range.start, range.end)),
                        });
                        let site = u32::try_from(sites.len())
                            .map_err(|error| Failure::Message(error.to_string()))?;
                        let wrapper_name = format!("{}_wesl_test", call.call.ty.ident.name());
                        call.call.ty.ident = Ident::new(wrapper_name);
                        call.call.arguments.push(Spanned::new(
                            Expression::Literal(LiteralExpression::U32(site)),
                            span,
                        ));
                    }
                    continue;
                }
                pending.extend(Visit::<StatementNode>::visit_mut(&mut **statement));
            }
        }
        Ok(())
    }

    fn add_wrappers(
        &self,
        syntax: &mut TranslationUnit,
        sourcemap: &impl SourceMap,
        transformed: &TestTransform,
        result_name: &Ident,
    ) -> Result<(), Failure> {
        let mut wrappers = Vec::new();
        for declaration in &mut syntax.global_declarations {
            let span = declaration.span();
            let GlobalDeclaration::Function(function) = &mut **declaration else {
                continue;
            };
            function.attributes.retain(|attribute| {
                !matches!(&**attribute, Attribute::Custom(custom) if custom.name == "test")
            });
            let Some(wesl::sourcemap::SourceMapEntry { path: module, .. }) =
                sourcemap.item(&function.ident.name())
            else {
                continue;
            };
            if module == &transformed.assertion_module || module == &transformed.result_module {
                let assertion = self.assertions.get(&*function.ident.name());
                if let Some((_, parameter_type)) = assertion {
                    let (parameter, parameter_type) = assertion_parameter(
                        function,
                        parameter_type.as_ref(),
                        module,
                        span,
                        sourcemap,
                    )?;
                    let (value_kind, components) =
                        assertion_kind(parameter_type, module, span, sourcemap)?;
                    if !self.referenced_assertions.contains(&*function.ident.name()) {
                        continue;
                    }
                    let wrapper =
                        assertion_wrapper(function, parameter, value_kind, components, result_name);
                    wrappers.push(wrapper.into());
                }
            }
        }
        syntax.global_declarations.extend(wrappers);
        Ok(())
    }

    fn finish(
        mut self,
        mut result: wesl::CompileResult,
        sourcemap: &impl SourceMap,
        transformed: &TestTransform,
    ) -> Result<CompiledTest, Failure> {
        let Some(compiled_entry) = self.compiled_entry.take() else {
            return Ok(None);
        };
        let result_name = self
            .result_name
            .take()
            .map(Ident::new)
            .ok_or_else(|| Failure::Message("shader test result is missing".to_owned()))?;
        self.rewrite_calls(&mut result.syntax, sourcemap, transformed)?;
        self.add_wrappers(&mut result.syntax, sourcemap, transformed, &result_name)?;
        let (buffers, resources) = place_buffers(
            &mut result.syntax,
            sourcemap,
            &transformed.root,
            &compiled_entry,
            &transformed.reserved,
        )?;
        let result_type = self
            .result_type
            .ok_or_else(|| Failure::Message("shader test result type is missing".to_owned()))?;
        let buffer_size = result_type.size_of().ok_or_else(|| {
            Failure::Message("shader test result requires a fixed buffer size".to_owned())
        })?;
        Ok(Some((
            result.to_string(),
            compiled_entry,
            self.sites,
            source_names(&result.syntax, sourcemap),
            TestLayout {
                result_type,
                buffer_size,
                cooperative: transformed.cooperative,
                buffers: buffers
                    .into_iter()
                    .filter_map(|(reached, buffer)| reached.then_some(buffer))
                    .collect(),
                resources,
            },
        )))
    }
}

fn assertion_type(
    value_type: Option<&TypeExpression>,
    module: &ModulePath,
    span: Span,
    sourcemap: &impl SourceMap,
    context: &mut Context<'_>,
) -> Result<Option<Type>, Failure> {
    value_type
        .map(|value_type| resolve_assertion_type(value_type, context))
        .transpose()
        .map_err(|error| {
            Failure::from_diagnostic(
                wesl::error::Diagnostic::from(error)
                    .with_module_path(
                        module.clone(),
                        sourcemap.display_name(module).map(str::to_owned),
                    )
                    .with_span(span)
                    .with_sourcemap(sourcemap),
            )
        })
}

#[expect(
    clippy::too_many_lines,
    reason = "Type resolution checks cycles, evaluates layout constants, and verifies alignment"
)]
fn resolve_assertion_type(
    value_type: &TypeExpression,
    context: &mut Context<'_>,
) -> Result<Type, wesl::Error> {
    let mut pending = vec![(value_type, false)];
    let mut active = HashSet::new();
    let mut checked = HashSet::new();
    let mut constants = Vec::new();
    while let Some((ty, exiting)) = pending.pop() {
        let name = ty.ident.name().to_string();
        if exiting {
            active.remove(&name);
            if let Some(
                declaration @ GlobalDeclaration::Declaration(Declaration {
                    kind: DeclarationKind::Const,
                    ..
                }),
            ) = context.source().user_decl(&name)
            {
                constants.push(declaration.clone());
            }
            continue;
        }
        pending.extend(Visit::<TypeExpression>::visit(ty).map(|child| (child, false)));
        if let Some(
            declaration @ (GlobalDeclaration::TypeAlias(_)
            | GlobalDeclaration::Struct(_)
            | GlobalDeclaration::Declaration(Declaration {
                kind: DeclarationKind::Const,
                ..
            })),
        ) = context.source().user_decl(&name)
        {
            if active.contains(&name) {
                return Err(wesl::Error::from(wesl::error::ValidateError::Cycle(
                    name.clone(),
                    name,
                )));
            }
            if checked.insert(name.clone()) {
                active.insert(name);
                pending.push((ty, true));
                pending.extend(
                    Visit::<TypeExpression>::visit(declaration).map(|child| (child, false)),
                );
            }
        }
    }
    for constant in constants {
        constant.exec(context)?;
    }
    let resolved_type = ty_eval_ty(value_type, context)?;
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
}

fn assertion_parameter<'a>(
    function: &'a Function,
    parameter_type: Option<&'a Type>,
    module: &ModulePath,
    span: Span,
    sourcemap: &impl SourceMap,
) -> Result<(&'a FormalParameter, &'a Type), Failure> {
    let Some((parameter, parameter_type)) =
        function
            .parameters
            .first()
            .zip(parameter_type)
            .filter(|(_, parameter_type)| {
                **parameter_type == Type::Bool || function.parameters.len() >= 2
            })
    else {
        let mut diagnostic = wesl::Error::Custom(
            "shader assertions require a bool first parameter or at least two parameters"
                .to_owned(),
        )
        .diagnostic()
        .with_module_path(
            module.clone(),
            sourcemap.display_name(module).map(str::to_owned),
        )
        .with_span(span);
        diagnostic.detail.source = sourcemap.source(module).map(str::to_owned);
        return Err(Failure::from_diagnostic(diagnostic));
    };
    Ok((parameter, parameter_type))
}

fn assertion_kind(
    parameter_type: &Type,
    module: &ModulePath,
    span: Span,
    sourcemap: &impl SourceMap,
) -> Result<(u32, u8), Failure> {
    let (value_kind, components): (u32, u8) = match parameter_type {
        Type::Bool => (0, 1),
        Type::U32 => (1, 1),
        Type::F32 => (2, 1),
        Type::I32 => (3, 1),
        Type::Vec(components, scalar) if **scalar == Type::U32 => (1, *components),
        Type::Vec(components, scalar) if **scalar == Type::F32 => (2, *components),
        Type::Vec(components, scalar) if **scalar == Type::I32 => (3, *components),
        _ => {
            return Err(Failure::from_diagnostic(
                wesl::Error::Custom(
                    "shader assertion values require bool, u32, i32, f32, or a vector of them"
                        .to_owned(),
                )
                .diagnostic()
                .with_module_path(
                    module.clone(),
                    sourcemap.display_name(module).map(str::to_owned),
                )
                .with_span(span)
                .with_sourcemap(sourcemap),
            ));
        }
    };
    Ok((value_kind, components))
}

fn assertion_bits(
    function: &Function,
    parameter: &FormalParameter,
    value_kind: u32,
    components: u8,
) -> (Expression, Expression) {
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
    (actual, expected)
}

fn assertion_wrapper(
    function: &Function,
    parameter: &FormalParameter,
    value_kind: u32,
    components: u8,
    result_name: &Ident,
) -> GlobalDeclaration {
    let call = Statement::FunctionCall(FunctionCallStatement {
        attributes: Vec::new(),
        call: FunctionCall {
            ty: function.ident.clone().into(),
            arguments: function
                .parameters
                .iter()
                .map(|parameter| Expression::from(parameter.ident.clone()).into())
                .collect(),
        },
    });
    let (actual, expected) = assertion_bits(function, parameter, value_kind, components);
    let components = u32::from(components);
    let location = available_name("wesl_test_location".to_owned(), |location| {
        function
            .parameters
            .iter()
            .any(|parameter| parameter.ident.name().as_str() == location)
    });
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
        wrapper_function
            .parameters
            .splice(0..0, function.parameters.iter().cloned());
    }
    wrapper
}

#[pyo3_stub_gen::derive::gen_stub_pyfunction(module = "wesl._native")]
#[pyfunction]
#[pyo3(signature = (compiler, root, test_name, options, result_binding, reserved, parsed_module=None))]
pub(super) fn compile_test(
    py: Python<'_>,
    #[gen_stub(override_type(type_repr="wesl.Compiler", imports=("wesl")))] compiler: Compiler<'_>,
    root: String,
    test_name: String,
    #[gen_stub(override_type(type_repr="wesl.TestOptions", imports=("wesl")))] options: TestOptions<
        '_,
    >,
    result_binding: u32,
    reserved: Vec<u32>,
    parsed_module: Option<&ParsedTestModule>,
) -> PyResult<CompiledTest> {
    if options.lower {
        return Err(PyNotImplementedError::new_err("lowering is not supported"));
    }
    let (_, sources) = compiler.split()?;
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
        let resolver = ModuleResolver::new(sources)?;
        let syntax = parsed_module
            .filter(|parsed_module| {
                resolver
                    .resolve_source(&root)
                    .is_ok_and(|source| source == parsed_module.source)
            })
            .map(|parsed_module| crate::compiler::clone_syntax(&parsed_module.syntax));
        let Some(PreparedTest {
            transformed,
            parsed_modules,
            syntax,
        }) = TestTransform::prepare(
            root,
            test_name,
            result_binding,
            reserved,
            &features,
            &resolver,
            syntax,
        )?
        else {
            return Ok(None);
        };
        let result = transformed.compile(
            &wesl::CompileOptions {
                imports: true,
                visibility,
                condcomp: true,
                strip,
                lower: false,
                validate,
                keep: Some(vec![transformed.entry_point.clone()]),
                keep_main: false,
                mangle_main: true,
                features,
                ..Default::default()
            },
            &resolver,
            parsed_modules,
        );
        drop(syntax);
        result
    })
    .map_err(|failure: Failure| failure.into_pyerr(py))
}

#[pyo3_stub_gen::derive::gen_stub_pyfunction(module = "wesl._native")]
#[pyfunction]
#[expect(
    clippy::too_many_lines,
    reason = "CPU execution initializes shader state, overrides, and the assertion buffer"
)]
pub(super) fn execute_test_cpu(
    py: Python<'_>,
    source: String,
    entry_point: String,
    layout: &TestLayout,
) -> PyResult<Vec<u8>> {
    if layout.cooperative {
        return Err(PyNotImplementedError::new_err(
            "CPU tests do not support builtin parameters or explicit workgroup sizes",
        ));
    }
    let result_type = layout.result_type.clone();
    py.detach(move || {
        let mut syntax = source.parse::<TranslationUnit>().map_err(|error| {
            Failure::from_diagnostic(
                wesl::error::Diagnostic::from(error).with_source(source.clone()),
            )
        })?;
        pass::retarget_idents(&mut syntax);
        let mut referenced = HashSet::new();
        Visit::<TypeExpression>::visit_rec(&syntax, &mut |expression: &TypeExpression| {
            referenced.insert(expression.ident.name().to_string());
        });
        for declaration in &mut syntax.global_declarations {
            if let GlobalDeclaration::Declaration(value) = &mut **declaration
                && value.kind == DeclarationKind::Override
                && value.initializer.is_none()
                && !referenced.contains(&*value.ident.name())
                && let Some(value_type) = &value.ty
            {
                value.initializer = Some(
                    format!("{value_type}()")
                        .parse::<Expression>()
                        .map_err(|error| Failure::from_diagnostic(error.into()))?
                        .into(),
                );
            }
        }
        let mut storage_count = 0;
        for declaration in &syntax.global_declarations {
            if matches!(
                &**declaration,
                GlobalDeclaration::Declaration(Declaration {
                    kind: DeclarationKind::Var(Some((AddressSpace::Storage, _))),
                    ..
                })
            ) {
                storage_count += 1;
            }
            if let GlobalDeclaration::Declaration(declaration) = &**declaration
                && (storage_count > 1
                    || matches!(
                        declaration.kind,
                        DeclarationKind::Var(
                            None | Some((
                                AddressSpace::Handle
                                    | AddressSpace::Immediate
                                    | AddressSpace::Workgroup
                                    | AddressSpace::Uniform,
                                _
                            ))
                        )
                    ))
            {
                return Err(Failure::Message(
                    "CPU tests do not support user resources or workgroup variables".to_owned(),
                ));
            }
        }
        let result = Instance::storable_zero_value(&result_type)
            .map_err(|error| Failure::from_diagnostic(wesl::eval::EvalError::from(error).into()))?;
        let result = RefInstance::new(result, AddressSpace::Storage, AccessMode::ReadWrite);
        let mut context = Context::new(&syntax);
        syntax.exec(&mut context).map_err(|error| {
            Failure::from_diagnostic(
                wesl::error::Diagnostic::from(error)
                    .with_ctx(&context)
                    .with_source(source.clone()),
            )
        })?;
        let expression = format!("{entry_point}()")
            .parse::<Expression>()
            .map_err(|error| Failure::from_diagnostic(error.into()))?;
        let (execution, context) = wesl::exec(
            &expression,
            &syntax,
            HashMap::from([((0, 0), result.clone())]),
            HashMap::new(),
        );
        execution.map_err(|error| {
            Failure::from_diagnostic(
                wesl::error::Diagnostic::from(error)
                    .with_ctx(&context)
                    .with_source(source),
            )
        })?;
        result
            .read()
            .map_err(|error| Failure::from_diagnostic(wesl::eval::EvalError::from(error).into()))?
            .to_buffer()
            .ok_or_else(|| Failure::Message("cannot encode CPU test result".to_owned()))
    })
    .map_err(|failure: Failure| failure.into_pyerr(py))
}
