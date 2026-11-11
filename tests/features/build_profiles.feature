Feature: Build profiles report what was compiled

  @native
  Scenario: A native-only build reports no Polars backend
    Given the facade compiled without default features
    When a consumer reads the build profile
    Then the profile reports the native backend
    And the profile does not report a Polars backend
    And the profile does not report the macro feature
    And the profile reports the target usize width

  @macros
  Scenario: A macros-only build reports the macro feature and no Polars backend
    Given the facade compiled without default features but with the macros feature
    When a consumer reads the build profile
    Then the profile reports the native backend
    And the profile does not report a Polars backend
    And the profile reports the macro feature
    And the profile reports the target usize width

  @polars
  Scenario: The default build reports the Polars backend
    Given the facade compiled with default features
    When a consumer reads the build profile
    Then the profile reports the native backend
    And the profile reports a Polars backend
    And the profile reports the macro feature

  @polars-only
  Scenario: A Polars-only build reports the Polars backend and no macro feature
    Given the facade compiled without default features but with the polars feature
    When a consumer reads the build profile
    Then the profile reports the native backend
    And the profile reports a Polars backend
    And the profile does not report the macro feature
    And the profile reports the target usize width
