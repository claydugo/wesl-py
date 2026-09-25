# Visit skips plain else branches for statements and expressions

`Visit<StatementNode>` and `Visit<ExpressionNode>` skip the body of a plain
`else` branch. Both visit `if` and `else if` bodies.

I reproduce this with the published `wesl` 0.5.0 crate.
The omission is also present in
[main at 38b8f0c](https://github.com/webgpu-tools/wesl-rs/blob/38b8f0c38b29bc84be7438e6dc086e1e217d0c0e/crates/wesl/src/pass/visit.rs#L299).

## Reproduction

`Cargo.toml`:

```toml
[package]
name = "wesl-visitor-reproduction"
version = "0.1.0"
edition = "2024"

[dependencies]
wesl = { version = "=0.5.0", default-features = false }
```

`src/main.rs`:

```rust
use wesl::{
    pass::Visit,
    syntax::{Expression, ExpressionNode, LiteralExpression, Statement, StatementNode},
};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let statement: Statement = "
        if false { return 1; }
        else if false { return 2; }
        else { return 3; }
    ".parse()?;
    let returns = Visit::<StatementNode>::visit(&statement)
        .filter(|statement| matches!(&***statement, Statement::Return(_)))
        .count();
    let integers: Vec<_> = Visit::<ExpressionNode>::visit(&statement)
        .filter_map(|expression| match &**expression {
            Expression::Literal(LiteralExpression::AbstractInt(value)) => Some(*value),
            _ => None,
        })
        .collect();
    println!("return statements: {returns}; integer literals: {integers:?}");
    assert_eq!(returns, 3);
    assert_eq!(integers, [1, 2, 3]);
    Ok(())
}
```

Run `cargo run`. It prints this output and fails the first assertion:

```text
return statements: 2; integer literals: [1, 2]
```

Expected output:

```text
return statements: 3; integer literals: [1, 2, 3]
```

## Cause and proposed fix

The `Statement::If` arms omit `else_clause` in both
[expression traversal](https://github.com/webgpu-tools/wesl-rs/blob/38b8f0c38b29bc84be7438e6dc086e1e217d0c0e/crates/wesl/src/pass/visit.rs#L299)
and
[statement traversal](https://github.com/webgpu-tools/wesl-rs/blob/38b8f0c38b29bc84be7438e6dc086e1e217d0c0e/crates/wesl/src/pass/visit.rs#L346).
The macro uses the same query for `visit` and `visit_mut`.

Add traversal of `else_clause` and its body in both implementations.
Add regression tests for immutable and mutable traversal, including nested
`else` bodies.

This prevents Python bindings from using the upstream visitor for shader assertion
instrumentation. An assertion inside a plain `else` must receive instrumentation
in the same way as an assertion inside `if` or `else if`.
