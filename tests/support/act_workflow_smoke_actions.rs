//! Fixture action interfaces for the production-derived Act smoke.

use std::fmt::Write;

/// Defines the interface that one replaced action exposes to later steps.
pub(super) fn fixture_action(
    index: usize,
    inputs: &[(&str, &str)],
) -> Result<String, std::fmt::Error> {
    let mut source =
        format!("name: Fixture action {index}\ndescription: Controlled workflow interface\n");
    write_input_declarations(&mut source, inputs)?;
    source.push_str("runs:\n  using: composite\n  steps:\n    - shell: bash\n      run: |\n");
    write_log_command(&mut source, index, inputs)?;
    source.push_str(index_specific_step(index));
    Ok(source)
}

/// Declares each input as optional, omitting the `inputs:` key when there are none.
fn write_input_declarations(
    source: &mut String,
    inputs: &[(&str, &str)],
) -> Result<(), std::fmt::Error> {
    if inputs.is_empty() {
        return Ok(());
    }
    source.push_str("inputs:\n");
    for (key, _) in inputs {
        writeln!(source, "  {key}:\n    required: false")?;
    }
    Ok(())
}

/// Writes the command that appends the action's index, directory and inputs to the smoke log.
fn write_log_command(
    source: &mut String,
    index: usize,
    inputs: &[(&str, &str)],
) -> Result<(), std::fmt::Error> {
    write!(source, "        printf '%s\\0' 'action-{index}' \"$PWD\" ")?;
    for (key, _) in inputs {
        write!(source, "\"${{{{ inputs.{key} }}}}\" ")?;
    }
    source.push_str("'__END__' >> \"$GITHUB_WORKSPACE/smoke.log\"\n");
    Ok(())
}

/// Returns the extra step the first two fixture actions run, or nothing.
const fn index_specific_step(index: usize) -> &'static str {
    match index {
        0 => "        echo \"$GITHUB_WORKSPACE/fixture-bin\" >> \"$GITHUB_PATH\"\n",
        1 => "        echo 'RUSTFLAGS=' >> \"$GITHUB_ENV\"\n",
        _ => "",
    }
}
