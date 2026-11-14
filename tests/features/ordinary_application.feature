Feature: The ordinary application path reports each failure at its own stage

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
