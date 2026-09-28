// From the WESL project's wgsl-test package.
// https://github.com/webgpu-tools/wesl-js/blob/37db2325b40cdb8aa504582cbc01cb4d41109a36/packages/wgsl-test/shaders/TestResult.wesl
// SPDX-License-Identifier: MIT
// See LICENSE in the wesl-py distribution.

public struct TestResult {
  passed: u32,
  failCount: u32,
  actual: vec4f,
  expected: vec4f,
}

@group(0) @binding(0) public var<storage, read_write> testResult: TestResult;

public fn initTestResult() {
  testResult.passed = 1u;
  testResult.failCount = 0u;
}
