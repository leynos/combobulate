"""Compose the executable identity tuple a kernel proof record is about.

DL-14 of the 1.2.2 ExecPlan fixes what "the same operation" means across the
catalogue, the facade and the verified body: a catalogue id, the operation the
facade dispatches, a dtype, the kernel symbol, a digest of the executable file,
a digest of the specification file, and the semantic policy the two must
agree on.

The tuple lives here rather than in the driver so the driver stays a pipeline
and this file stays a statement of identity. It reads no file and runs no
solver: the caller supplies the two digests it has already computed, and this
module only says what they are digests *of*.

For example, ``make verus-kernel`` writes the tuple into
``tools/verifier-fixtures/verus-kernel/provenance.json`` beside the
observations it identifies.
"""

from __future__ import annotations

# The catalogue entry that specifies elementwise addition.
CATALOGUE_ID = "V001"

# The verb a user writes for that entry.
OPERATION = "add"

# The element type this record is about; other dtypes are later tasks.
DTYPE = "I64"

# The shipped function the facade's dispatch calls.
SYMBOL = "combobulate_kernel::elementwise_add::add_i64_into"

# The semantic policy both the executable and its specification state.
POLICY = "checked-i64"

# The file that holds the shipped body and the file that specifies it.
EXECUTABLE = "crates/combobulate-kernel/src/elementwise_add.rs"
SPECIFICATION = "crates/combobulate-kernel/verus/elementwise_add_contract.rs"


def identity(executable_digest: str, specification_digest: str) -> dict:
    """Return the identity tuple binding this record to one operation.

    The two digests are structural, so they survive re-formatting but change
    when the code does, which is what makes the record a statement about the
    body a reader can still find::

        >>> tuple_ = identity('ast-sha256:aa', 'ast-sha256:bb')
        >>> tuple_['operation']['catalogue_id'] == tuple_['catalogue_id']
        True
    """
    return {
        "catalogue_id": CATALOGUE_ID,
        "operation": {"name": OPERATION, "catalogue_id": CATALOGUE_ID},
        "dtype": DTYPE,
        "symbol": SYMBOL,
        "executable": {"path": EXECUTABLE, "digest": executable_digest},
        "specification": {"path": SPECIFICATION, "digest": specification_digest},
        "semantic_policy": POLICY,
    }
