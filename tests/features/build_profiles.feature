Feature: Build profiles report what was compiled

  @native
  Scenario: A native-only build reports no Polars backend
    Given the facade compiled without default features
    When a consumer reads the build profile
    Then the profile reports the native backend
    And the profile does not report a Polars backend
    And the profile does not report the macro feature
    And the profile reports the target usize width

  @polars
  Scenario: The default build reports the Polars backend
    Given the facade compiled with default features
    When a consumer reads the build profile
    Then the profile reports the native backend
    And the profile reports a Polars backend
    And the profile reports the macro feature
