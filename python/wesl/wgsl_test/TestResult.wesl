struct TestResult {
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
