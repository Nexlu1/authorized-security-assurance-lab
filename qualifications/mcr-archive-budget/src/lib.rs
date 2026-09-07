use std::io::{self, Read};

pub type BoxError = Box<dyn std::error::Error + Send + Sync + 'static>;
pub type Result<T> = std::result::Result<T, BoxError>;

#[derive(Debug, Clone, Copy)]
pub struct ArchiveByteBudgetPolicy {
    pub max_member_actual_bytes: u64,
    pub max_total_actual_bytes: u64,
}

#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct ArchiveByteBudgetSummary {
    pub members_verified: u64,
    pub actual_uncompressed_bytes: u64,
}

struct ActualByteBudgetReader<'a, R> {
    inner: R,
    member_limit: u64,
    total_limit: u64,
    member_actual: u64,
    total_actual: &'a mut u64,
}

impl<'a, R> ActualByteBudgetReader<'a, R> {
    fn new(inner: R, member_limit: u64, total_limit: u64, total_actual: &'a mut u64) -> Self {
        Self { inner, member_limit, total_limit, member_actual: 0, total_actual }
    }
}

impl<R: Read> Read for ActualByteBudgetReader<'_, R> {
    fn read(&mut self, buf: &mut [u8]) -> io::Result<usize> {
        if buf.is_empty() {
            return Ok(0);
        }
        let member_remaining = self.member_limit.saturating_sub(self.member_actual);
        let total_remaining = self.total_limit.saturating_sub(*self.total_actual);
        let allowed_u64 = member_remaining.min(total_remaining).min(buf.len() as u64);
        if allowed_u64 == 0 {
            let mut probe = [0u8; 1];
            return match self.inner.read(&mut probe)? {
                0 => Ok(0),
                _ if self.member_actual >= self.member_limit => Err(io::Error::other(format!(
                    "archive member actual-byte budget exceeded: limit={} actual_at_least={}",
                    self.member_limit,
                    self.member_actual.saturating_add(1)
                ))),
                _ => Err(io::Error::other(format!(
                    "archive total actual-byte budget exceeded: limit={} actual_at_least={}",
                    self.total_limit,
                    (*self.total_actual).saturating_add(1)
                ))),
            };
        }
        let allowed = usize::try_from(allowed_u64).unwrap_or(buf.len());
        let n = self.inner.read(&mut buf[..allowed])?;
        let n_u64 = u64::try_from(n).map_err(io::Error::other)?;
        self.member_actual = self.member_actual.checked_add(n_u64)
            .ok_or_else(|| io::Error::other("archive member actual-byte counter overflow"))?;
        *self.total_actual = (*self.total_actual).checked_add(n_u64)
            .ok_or_else(|| io::Error::other("archive total actual-byte counter overflow"))?;
        Ok(n)
    }
}

pub fn verify_zip_actual_byte_budgets_bytes(
    bytes: &[u8],
    policy: ArchiveByteBudgetPolicy,
) -> Result<ArchiveByteBudgetSummary> {
    let archive = rawzip::ZipArchive::from_slice(bytes)?;
    let expected_entries = archive.entries_hint();
    let mut entries = archive.entries();
    let mut entries_seen = 0u64;
    let mut actual_total = 0u64;
    let mut members_verified = 0u64;

    while let Some(entry) = entries.next_entry()? {
        entries_seen = entries_seen.checked_add(1).ok_or("archive entry counter overflow")?;
        if entries_seen > expected_entries {
            return Err(format!(
                "ZIP central-directory entry count exceeded EOCD hint: expected {expected_entries}, observed at least {entries_seen}"
            ).into());
        }
        if entry.is_dir() {
            continue;
        }
        if entry.flags().is_encrypted() || entry.compression_method() == rawzip::CompressionMethod::AES {
            return Err("encrypted archive member is outside bounded verification path".into());
        }

        let local_entry = archive.get_entry(entry.wayfinder())?;
        let reader = local_entry.reader();
        match entry.compression_method() {
            rawzip::CompressionMethod::STORE => {
                let budget = ActualByteBudgetReader::new(
                    reader,
                    policy.max_member_actual_bytes,
                    policy.max_total_actual_bytes,
                    &mut actual_total,
                );
                let mut verifier = local_entry.verifying_reader(budget);
                io::copy(&mut verifier, &mut io::sink())?;
            }
            rawzip::CompressionMethod::DEFLATE => {
                let decoder = flate2::read::DeflateDecoder::new(reader);
                let budget = ActualByteBudgetReader::new(
                    decoder,
                    policy.max_member_actual_bytes,
                    policy.max_total_actual_bytes,
                    &mut actual_total,
                );
                let mut verifier = local_entry.verifying_reader(budget);
                io::copy(&mut verifier, &mut io::sink())?;
            }
            method => {
                return Err(format!(
                    "compression method outside bounded verification allowlist: {}",
                    method.as_u16()
                ).into());
            }
        }
        members_verified = members_verified.checked_add(1)
            .ok_or("archive verified-member counter overflow")?;
    }

    if entries_seen != expected_entries {
        return Err(format!(
            "ZIP central-directory entry count mismatch: EOCD expected {expected_entries}, iterator observed {entries_seen}"
        ).into());
    }

    Ok(ArchiveByteBudgetSummary {
        members_verified,
        actual_uncompressed_bytes: actual_total,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    const STORE_ZIP: &[u8] = &[80,75,3,4,20,0,0,0,0,0,224,117,39,93,58,112,129,57,10,0,0,0,10,0,0,0,5,0,0,0,97,46,116,120,116,97,98,99,100,101,102,103,104,105,106,80,75,1,2,20,3,20,0,0,0,0,0,224,117,39,93,58,112,129,57,10,0,0,0,10,0,0,0,5,0,0,0,0,0,0,0,0,0,0,0,128,1,0,0,0,0,97,46,116,120,116,80,75,5,6,0,0,0,0,1,0,1,0,51,0,0,0,45,0,0,0,0,0];
    const DEFLATE_ZIP: &[u8] = &[80,75,3,4,20,0,0,0,8,0,224,117,39,93,100,122,112,175,6,0,0,0,100,0,0,0,5,0,0,0,97,46,116,120,116,75,76,164,61,0,0,80,75,1,2,20,3,20,0,0,0,8,0,224,117,39,93,100,122,112,175,6,0,0,0,100,0,0,0,5,0,0,0,0,0,0,0,0,0,0,0,128,1,0,0,0,0,97,46,116,120,116,80,75,5,6,0,0,0,0,1,0,1,0,51,0,0,0,41,0,0,0,0,0];
    const DISHONEST_ZIP: &[u8] = &[80,75,3,4,20,0,0,0,8,0,224,117,39,93,100,122,112,175,6,0,0,0,5,0,0,0,5,0,0,0,97,46,116,120,116,75,76,164,61,0,0,80,75,1,2,20,3,20,0,0,0,8,0,224,117,39,93,100,122,112,175,6,0,0,0,5,0,0,0,5,0,0,0,0,0,0,0,0,0,0,0,128,1,0,0,0,0,97,46,116,120,116,80,75,5,6,0,0,0,0,1,0,1,0,51,0,0,0,41,0,0,0,0,0];
    const TWO_STORE_ZIP: &[u8] = &[80,75,3,4,20,0,0,0,0,0,243,117,39,93,239,57,142,75,6,0,0,0,6,0,0,0,5,0,0,0,97,46,116,120,116,97,98,99,100,101,102,80,75,3,4,20,0,0,0,0,0,243,117,39,93,173,203,18,204,6,0,0,0,6,0,0,0,5,0,0,0,98,46,116,120,116,103,104,105,106,107,108,80,75,1,2,20,3,20,0,0,0,0,0,243,117,39,93,239,57,142,75,6,0,0,0,6,0,0,0,5,0,0,0,0,0,0,0,0,0,0,0,128,1,0,0,0,0,97,46,116,120,116,80,75,1,2,20,3,20,0,0,0,0,0,243,117,39,93,173,203,18,204,6,0,0,0,6,0,0,0,5,0,0,0,0,0,0,0,0,0,0,0,128,1,41,0,0,0,98,46,116,120,116,80,75,5,6,0,0,0,0,2,0,2,0,102,0,0,0,82,0,0,0,0,0];

    #[test]
    fn store_member_is_verified_without_materialisation() {
        let summary = verify_zip_actual_byte_budgets_bytes(STORE_ZIP, ArchiveByteBudgetPolicy {
            max_member_actual_bytes: 10,
            max_total_actual_bytes: 10,
        }).unwrap();
        assert_eq!(summary, ArchiveByteBudgetSummary { members_verified: 1, actual_uncompressed_bytes: 10 });
    }

    #[test]
    fn deflate_member_is_verified_without_materialisation() {
        let summary = verify_zip_actual_byte_budgets_bytes(DEFLATE_ZIP, ArchiveByteBudgetPolicy {
            max_member_actual_bytes: 100,
            max_total_actual_bytes: 100,
        }).unwrap();
        assert_eq!(summary, ArchiveByteBudgetSummary { members_verified: 1, actual_uncompressed_bytes: 100 });
    }

    #[test]
    fn arc_008_member_limit_fails_closed() {
        let err = verify_zip_actual_byte_budgets_bytes(DEFLATE_ZIP, ArchiveByteBudgetPolicy {
            max_member_actual_bytes: 50,
            max_total_actual_bytes: 1000,
        }).unwrap_err();
        assert!(err.to_string().contains("member actual-byte budget exceeded"));
    }

    #[test]
    fn arc_009_total_limit_is_cumulative_across_members() {
        let err = verify_zip_actual_byte_budgets_bytes(TWO_STORE_ZIP, ArchiveByteBudgetPolicy {
            max_member_actual_bytes: 10,
            max_total_actual_bytes: 10,
        }).unwrap_err();
        assert!(err.to_string().contains("total actual-byte budget exceeded"));
    }

    #[test]
    fn arc_011_hard_actual_byte_limit_wins_over_dishonest_metadata() {
        let err = verify_zip_actual_byte_budgets_bytes(DISHONEST_ZIP, ArchiveByteBudgetPolicy {
            max_member_actual_bytes: 10,
            max_total_actual_bytes: 1000,
        }).unwrap_err();
        assert!(err.to_string().contains("member actual-byte budget exceeded"));
    }
}
