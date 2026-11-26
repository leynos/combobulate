//! Materialized arrays and the dtype they report.
//!
//! An `Array` owns one immutable buffer and describes it with a dynamic dtype.
//! Storage is a private enum so a later dtype can be added without changing a
//! public signature, and the I64 buffer sits behind an `Arc` so an expression
//! can share it without copying. Nothing here computes: `Array` is a value, and
//! the arithmetic lives in the kernel behind [`Array::expr`].

use std::sync::Arc;

use crate::expr::AExpr;

/// The element type of an [`Array`].
///
/// Dtypes are dynamic metadata, not a type parameter: one `Array` type holds
/// every element type, and this value names which one its buffer holds.
///
/// ```
/// use combobulate::{Array, Dtype};
///
/// assert_eq!(
///     Array::from_i64(vec![1]).dtype(),
///     Dtype::I64,
///     "a buffer built from i64 values reports the I64 dtype"
/// );
/// ```
#[non_exhaustive]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Dtype {
    /// Signed 64-bit integers, added with checked overflow.
    I64,
}

/// The buffer an array holds, one variant per dtype.
#[derive(Clone, Debug)]
enum Storage {
    /// One shared, immutable I64 buffer.
    I64(Arc<Vec<i64>>),
}

impl Storage {
    /// The number of elements held, whatever the dtype.
    fn len(&self) -> usize {
        match self {
            Self::I64(values) => values.len(),
        }
    }

    /// The elements as an I64 slice.
    ///
    /// Infallible because I64 is the only dtype this release has: the public
    /// `Array::as_i64_slice` returns `Option` so a later dtype can answer
    /// `None`, and it is this method that will grow the arms then.
    fn i64_slice(&self) -> &[i64] {
        match self {
            Self::I64(values) => values.as_slice(),
        }
    }

    /// The dtype of the elements held.
    const fn dtype(&self) -> Dtype {
        match self {
            Self::I64(_) => Dtype::I64,
        }
    }
}

/// An immutable materialized array.
///
/// Construction moves a `Vec` into shared storage without copying its
/// elements, and cloning an array clones the handle rather than the data.
///
/// ```
/// use combobulate::Array;
///
/// let array = Array::from_i64(vec![10, 20]);
/// assert_eq!(array.len(), 2, "the array reports its element count");
/// assert_eq!(
///     array.as_i64_slice(),
///     Some(&[10_i64, 20][..]),
///     "the buffer is readable in place"
/// );
/// ```
#[derive(Clone, Debug)]
pub struct Array {
    /// The elements this array presents.
    storage: Storage,
}

impl Array {
    /// Build an array from owned I64 values, without copying them.
    ///
    /// # Examples
    ///
    /// ```
    /// use combobulate::Array;
    ///
    /// let empty = Array::from_i64(Vec::new());
    /// assert!(empty.is_empty(), "an array of no values is empty");
    /// ```
    #[must_use]
    pub fn from_i64(values: Vec<i64>) -> Self {
        Self {
            storage: Storage::I64(Arc::new(values)),
        }
    }

    /// Wrap a buffer the expression graph already shares.
    ///
    /// Execution produces its results as shared buffers, so wrapping one adds
    /// a handle rather than copying elements. That is why collecting an
    /// expression that is only an input returns the very buffer it was given
    /// (FACADE-3).
    pub(crate) const fn from_shared(values: Arc<Vec<i64>>) -> Self {
        Self {
            storage: Storage::I64(values),
        }
    }

    /// The dtype of the elements this array holds.
    #[must_use]
    pub const fn dtype(&self) -> Dtype { self.storage.dtype() }

    /// The number of elements this array holds.
    #[must_use]
    pub fn len(&self) -> usize { self.storage.len() }

    /// Whether this array holds no elements.
    #[must_use]
    pub fn is_empty(&self) -> bool { self.storage.len() == 0 }

    /// The elements as a slice, when the dtype is I64.
    ///
    /// The returned slice borrows the array's own buffer, so reading is not a
    /// copy. The answer is `Some` for every array this release can build,
    /// because I64 is its only dtype; the `Option` is what lets a later dtype
    /// answer `None` without changing this signature.
    #[must_use]
    pub fn as_i64_slice(&self) -> Option<&[i64]> { Some(self.storage.i64_slice()) }

    /// A deferred expression that yields this array.
    ///
    /// The expression shares this array's buffer, so building one copies no
    /// elements.
    ///
    /// # Examples
    ///
    /// ```
    /// use combobulate::Array;
    ///
    /// let array = Array::from_i64(vec![1, 2, 3]);
    /// let expression = array.expr();
    /// assert_eq!(
    ///     format!("{expression:?}"),
    ///     "input(3)",
    ///     "an array becomes one input node reporting its length"
    /// );
    /// ```
    #[must_use]
    pub fn expr(&self) -> AExpr {
        let Storage::I64(values) = &self.storage;
        AExpr::from_values(Arc::clone(values))
    }
}

#[cfg(test)]
mod tests {
    //! Construction and inspection of materialized arrays.

    use rstest::rstest;

    use super::{Array, Dtype};

    #[test]
    fn from_i64_reports_the_dtype_it_was_built_with() {
        assert_eq!(
            Array::from_i64(vec![1, 2]).dtype(),
            Dtype::I64,
            "an I64 buffer must report the I64 dtype"
        );
    }

    #[rstest]
    #[case::empty(vec![], 0, true)]
    #[case::one(vec![7], 1, false)]
    #[case::many(vec![1, 2, 3], 3, false)]
    fn len_and_is_empty_describe_the_buffer(
        #[case] values: Vec<i64>,
        #[case] expected_len: usize,
        #[case] expected_empty: bool,
    ) {
        let array = Array::from_i64(values);
        assert_eq!(
            array.len(),
            expected_len,
            "len must be the number of elements supplied"
        );
        assert_eq!(
            array.is_empty(),
            expected_empty,
            "is_empty must agree with the element count"
        );
    }

    #[rstest]
    #[case::empty(vec![])]
    #[case::one(vec![7])]
    #[case::many(vec![4, 5, 6])]
    fn construction_keeps_the_vectors_original_buffer(#[case] values: Vec<i64>) {
        let original = values.as_ptr();
        let array = Array::from_i64(values);
        assert_eq!(
            array.as_i64_slice().map(<[i64]>::as_ptr),
            Some(original),
            "moving a Vec into an Array must not copy its elements (FACADE-3)"
        );
    }

    #[test]
    fn the_slice_reads_the_supplied_values_in_order() {
        let array = Array::from_i64(vec![3, 1, 2]);
        assert_eq!(
            array.as_i64_slice(),
            Some(&[3_i64, 1, 2][..]),
            "the slice must present the values as supplied"
        );
    }
}
