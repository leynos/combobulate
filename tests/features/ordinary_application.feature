Feature: Ordinary application of identity and add to I64 vectors

  Scenario: Identity shares the input buffer
    Given an I64 vector [1, 2, 3]
    When identity is applied and the expression is collected
    Then the result is [1, 2, 3]
    And the result shares the input buffer

  Scenario: Adding two vectors after explicit preparation
    Given an I64 vector [1, 2, 3]
    And another I64 vector [10, 20, 30]
    When add is applied, the expression is prepared, and the plan is executed
    Then the result is [11, 22, 33]
    And both inputs are unchanged

  Scenario: Adding empty vectors
    Given an I64 vector []
    And another I64 vector []
    When add is applied and the expression is collected
    Then the result is []

  Scenario: Mismatched lengths fail at preparation
    Given an I64 vector [1, 2, 3]
    And another I64 vector [1, 2]
    When add is applied and the expression is prepared
    Then preparation fails with ShapeAgreement between lengths 3 and 2

  Scenario: A shape disagreement is reported before execution
    Given two arrays of different lengths
    When a consumer prepares their sum
    Then the preparation reports a shape disagreement
    And the reported stage is preparation

  Scenario: An overflow is reported only from execution
    Given two arrays whose sum overflows
    When a consumer prepares and then executes their sum
    Then the preparation succeeds
    And the execution reports an integer overflow
    And the reported stage is execution

  Scenario: Overflow fails at execution, not preparation
    Given an I64 vector [0, 9223372036854775807]
    And another I64 vector [0, 1]
    When add is applied and the expression is prepared
    Then preparation succeeds
    And executing the plan fails with IntegerOverflow at position 1
