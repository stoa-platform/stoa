use std::{
    collections::BTreeMap,
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    path::{Path, PathBuf},
    time::Duration,
};

use chrono::Utc;
use parking_lot::Mutex;
use serde::{Deserialize, Serialize};
use thiserror::Error;
use uuid::Uuid;

use super::AuditEvent;

const SEGMENT_EXT: &str = "seg";

#[derive(Clone, Debug)]
pub struct SpoolConfig {
    pub dir: PathBuf,
    pub capacity_bytes: u64,
    pub segment_bytes: u64,
    pub high_water_pct: u8,
}

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct SpoolCursor {
    pub segment_id: u64,
    pub offset: usize,
}

#[derive(Debug, Error)]
pub enum SpoolError {
    #[error("audit spool gap declared: {0}")]
    GapDeclared(String),
}

pub struct AuditSpool {
    config: SpoolConfig,
    state: Mutex<SpoolState>,
}

#[derive(Default)]
struct SpoolState {
    records: Vec<StoredRecord>,
    segments: BTreeMap<u64, SegmentState>,
    active_segment: u64,
    bytes_on_disk: u64,
}

struct StoredRecord {
    cursor: SpoolCursor,
    event: AuditEvent,
    bytes: u64,
    acked: bool,
}

#[derive(Default)]
struct SegmentState {
    bytes: u64,
    event_count: usize,
    acked_count: usize,
}

#[derive(Serialize, Deserialize)]
struct WalRecord {
    idempotency_key: Uuid,
    #[serde(flatten)]
    event: AuditEvent,
}

impl AuditSpool {
    pub fn open(config: SpoolConfig) -> Result<Self, SpoolError> {
        fs::create_dir_all(&config.dir)
            .map_err(|err| SpoolError::GapDeclared(format!("create spool dir: {err}")))?;
        let state = recover(&config.dir)?;
        Ok(Self {
            config,
            state: Mutex::new(state),
        })
    }

    pub fn append(&self, mut event: AuditEvent) -> Result<(), SpoolError> {
        event.idempotency_key = Uuid::new_v4();
        let record = WalRecord {
            idempotency_key: event.idempotency_key,
            event: event.clone(),
        };
        let mut line = serde_json::to_vec(&record)
            .map_err(|err| SpoolError::GapDeclared(format!("serialize audit event: {err}")))?;
        line.push(b'\n');
        let line_len = line.len() as u64;

        let mut state = self.state.lock();
        if state.bytes_on_disk.saturating_add(line_len) > self.config.capacity_bytes {
            return Err(SpoolError::GapDeclared(
                "audit spool capacity exhausted".into(),
            ));
        }
        if state.active_segment == 0 {
            state.active_segment = 1;
        }
        let active_bytes = state
            .segments
            .get(&state.active_segment)
            .map_or(0, |segment| segment.bytes);
        if active_bytes > 0 && active_bytes.saturating_add(line_len) > self.config.segment_bytes {
            state.active_segment = state.active_segment.saturating_add(1);
        }

        let segment_id = state.active_segment;
        let path = segment_path(&self.config.dir, segment_id);
        let mut file = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&path)
            .map_err(|err| SpoolError::GapDeclared(format!("open segment: {err}")))?;
        file.write_all(&line)
            .and_then(|()| file.sync_all())
            .map_err(|err| SpoolError::GapDeclared(format!("durable append failed: {err}")))?;

        let segment = state.segments.entry(segment_id).or_default();
        let cursor = SpoolCursor {
            segment_id,
            offset: segment.event_count,
        };
        segment.bytes = segment.bytes.saturating_add(line_len);
        segment.event_count += 1;
        state.bytes_on_disk = state.bytes_on_disk.saturating_add(line_len);
        state.records.push(StoredRecord {
            cursor,
            event,
            bytes: line_len,
            acked: false,
        });
        Ok(())
    }

    pub fn drain_oldest(&self, max: usize) -> Vec<(SpoolCursor, AuditEvent)> {
        self.state
            .lock()
            .records
            .iter()
            .filter(|record| !record.acked)
            .take(max)
            .map(|record| (record.cursor, record.event.clone()))
            .collect()
    }

    pub fn ack(&self, cursor: SpoolCursor) -> Result<(), SpoolError> {
        let mut state = self.state.lock();
        if let Some(record) = state
            .records
            .iter_mut()
            .find(|record| record.cursor == cursor)
        {
            if !record.acked {
                record.acked = true;
                if let Some(segment) = state.segments.get_mut(&cursor.segment_id) {
                    segment.acked_count += 1;
                }
            }
        }
        compact_acked_segments(&self.config.dir, &mut state)
    }

    pub fn depth(&self) -> usize {
        self.state
            .lock()
            .records
            .iter()
            .filter(|record| !record.acked)
            .count()
    }

    pub fn oldest_age(&self) -> Option<Duration> {
        self.state
            .lock()
            .records
            .iter()
            .filter(|record| !record.acked)
            .map(|record| Utc::now().signed_duration_since(record.event.occurred_at))
            .filter_map(|age| age.to_std().ok())
            .max()
    }

    pub fn is_over_high_water(&self) -> bool {
        let state = self.state.lock();
        state.bytes_on_disk.saturating_mul(100)
            >= self
                .config
                .capacity_bytes
                .saturating_mul(self.config.high_water_pct as u64)
    }
}

fn recover(dir: &Path) -> Result<SpoolState, SpoolError> {
    let mut state = SpoolState::default();
    let mut segments = fs::read_dir(dir)
        .map_err(|err| SpoolError::GapDeclared(format!("read spool dir: {err}")))?
        .filter_map(Result::ok)
        .filter_map(|entry| segment_id(entry.path()).map(|id| (id, entry.path())))
        .collect::<Vec<_>>();
    segments.sort_by_key(|(id, _)| *id);
    let last_segment = segments.last().map(|(id, _)| *id);

    for (id, path) in segments {
        let is_last = Some(id) == last_segment;
        let records = recover_segment(id, &path, is_last)?;
        for (event, bytes) in records {
            let segment = state.segments.entry(id).or_default();
            let cursor = SpoolCursor {
                segment_id: id,
                offset: segment.event_count,
            };
            segment.event_count += 1;
            segment.bytes = segment.bytes.saturating_add(bytes);
            state.bytes_on_disk = state.bytes_on_disk.saturating_add(bytes);
            state.records.push(StoredRecord {
                cursor,
                event,
                bytes,
                acked: false,
            });
        }
        state.active_segment = id;
    }
    if state.active_segment == 0 {
        state.active_segment = 1;
    }
    Ok(state)
}

fn recover_segment(
    segment_id: u64,
    path: &Path,
    is_last: bool,
) -> Result<Vec<(AuditEvent, u64)>, SpoolError> {
    let mut data = Vec::new();
    File::open(path)
        .and_then(|mut file| file.read_to_end(&mut data))
        .map_err(|err| SpoolError::GapDeclared(format!("read segment: {err}")))?;
    if !data.ends_with(b"\n") {
        if !is_last {
            return Err(SpoolError::GapDeclared(format!(
                "segment {segment_id} has non-trailing partial record"
            )));
        }
        let truncate_at = data
            .iter()
            .rposition(|byte| *byte == b'\n')
            .map_or(0, |pos| pos + 1);
        File::options()
            .write(true)
            .open(path)
            .and_then(|file| file.set_len(truncate_at as u64))
            .map_err(|err| SpoolError::GapDeclared(format!("truncate partial record: {err}")))?;
        data.truncate(truncate_at);
    }

    let mut records = Vec::new();
    let mut start = 0;
    for (idx, byte) in data.iter().enumerate() {
        if *byte != b'\n' {
            continue;
        }
        let line = &data[start..idx];
        let bytes = (idx + 1 - start) as u64;
        start = idx + 1;
        if line.is_empty() {
            continue;
        }
        let mut record: WalRecord = serde_json::from_slice(line).map_err(|err| {
            SpoolError::GapDeclared(format!("corrupt segment {segment_id}: {err}"))
        })?;
        record.event.idempotency_key = record.idempotency_key;
        records.push((record.event, bytes));
    }
    Ok(records)
}

fn compact_acked_segments(dir: &Path, state: &mut SpoolState) -> Result<(), SpoolError> {
    let removable = state
        .segments
        .iter()
        .filter(|(_, segment)| {
            segment.event_count > 0 && segment.acked_count == segment.event_count
        })
        .map(|(id, _)| *id)
        .collect::<Vec<_>>();
    for segment_id in removable {
        fs::remove_file(segment_path(dir, segment_id))
            .map_err(|err| SpoolError::GapDeclared(format!("remove acked segment: {err}")))?;
        state.segments.remove(&segment_id);
        let removed_bytes = state
            .records
            .iter()
            .filter(|record| record.cursor.segment_id == segment_id)
            .map(|record| record.bytes)
            .sum::<u64>();
        state
            .records
            .retain(|record| record.cursor.segment_id != segment_id);
        state.bytes_on_disk = state.bytes_on_disk.saturating_sub(removed_bytes);
    }
    state.active_segment = state
        .segments
        .keys()
        .next_back()
        .copied()
        .unwrap_or(0)
        .max(1);
    Ok(())
}

fn segment_path(dir: &Path, id: u64) -> PathBuf {
    dir.join(format!("{id:08}.{SEGMENT_EXT}"))
}

fn segment_id(path: PathBuf) -> Option<u64> {
    (path.extension()?.to_str()? == SEGMENT_EXT)
        .then(|| path.file_stem()?.to_str()?.parse().ok())
        .flatten()
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeSet;

    use chrono::TimeZone;
    use serde_json::json;
    use tempfile::tempdir;

    use super::*;
    use crate::audit::AuditDecision;

    fn config(dir: PathBuf) -> SpoolConfig {
        SpoolConfig {
            dir,
            capacity_bytes: 4096,
            segment_bytes: 4096,
            high_water_pct: 80,
        }
    }

    fn event(i: u128) -> AuditEvent {
        AuditEvent {
            idempotency_key: Uuid::nil(),
            source: "stoa-gateway".into(),
            event_type: "TOOL_CALL_DECISION".into(),
            decision: AuditDecision::Deny,
            reason: format!("reason-{i}"),
            tenant_id: Uuid::from_u128(1),
            actor_id: Some(Uuid::from_u128(2)),
            session_id: Some("sid".into()),
            resource_type: "mcp_tool".into(),
            resource_id: format!("tool-{i}"),
            tool_call_id: Uuid::from_u128(3 + i),
            approval_id: None,
            policy_version: Some("policy-v1".into()),
            correlation_id: Uuid::from_u128(99 + i),
            occurred_at: Utc.timestamp_opt(1_700_000_000 + i as i64, 0).unwrap(),
            details: json!({ "n": i }),
        }
    }

    #[test]
    fn regression_audit_spool_survives_process_restart() {
        // regression for CAB-2227
        let dir = tempdir().unwrap();
        let spool = AuditSpool::open(config(dir.path().into())).unwrap();
        spool.append(event(1)).unwrap();
        spool.append(event(2)).unwrap();
        let idempotency_key = spool.drain_oldest(1)[0].1.idempotency_key;
        drop(spool);

        let recovered = AuditSpool::open(config(dir.path().into())).unwrap();
        let drained = recovered.drain_oldest(10);
        assert_eq!(drained.len(), 2);
        assert_eq!(drained[0].1.resource_id, "tool-1");
        assert_eq!(drained[1].1.resource_id, "tool-2");
        assert_eq!(drained[0].1.idempotency_key, idempotency_key);
        assert!(!drained[0].1.idempotency_key.is_nil());
    }

    #[test]
    fn regression_audit_spool_drain_is_oldest_first() {
        // regression for CAB-2227
        let dir = tempdir().unwrap();
        let spool = AuditSpool::open(config(dir.path().into())).unwrap();
        for i in 1..=3 {
            spool.append(event(i)).unwrap();
        }
        let ids = spool
            .drain_oldest(3)
            .into_iter()
            .map(|(_, event)| event.resource_id)
            .collect::<Vec<_>>();
        assert_eq!(ids, ["tool-1", "tool-2", "tool-3"]);
    }

    #[test]
    fn regression_audit_spool_segment_removed_only_after_all_acked() {
        // regression for CAB-2227
        let dir = tempdir().unwrap();
        let spool = AuditSpool::open(config(dir.path().into())).unwrap();
        spool.append(event(1)).unwrap();
        spool.append(event(2)).unwrap();
        let drained = spool.drain_oldest(2);
        spool.ack(drained[0].0).unwrap();
        assert!(segment_path(dir.path(), 1).exists());
        spool.ack(drained[1].0).unwrap();
        assert!(!segment_path(dir.path(), 1).exists());
    }

    #[test]
    fn regression_audit_spool_reports_over_high_water_at_threshold() {
        // regression for CAB-2227
        let dir = tempdir().unwrap();
        let spool = AuditSpool::open(SpoolConfig {
            capacity_bytes: 700,
            high_water_pct: 50,
            ..config(dir.path().into())
        })
        .unwrap();
        spool.append(event(1)).unwrap();
        assert!(spool.is_over_high_water());
    }

    #[test]
    fn regression_audit_spool_append_fails_loud_when_capacity_exhausted() {
        // regression for CAB-2227
        let dir = tempdir().unwrap();
        let spool = AuditSpool::open(SpoolConfig {
            capacity_bytes: 64,
            ..config(dir.path().into())
        })
        .unwrap();
        assert!(matches!(
            spool.append(event(1)),
            Err(SpoolError::GapDeclared(_))
        ));
        assert_eq!(spool.depth(), 0);
    }

    #[test]
    fn regression_audit_spool_recovers_partial_trailing_record() {
        // regression for CAB-2227
        let dir = tempdir().unwrap();
        let spool = AuditSpool::open(config(dir.path().into())).unwrap();
        spool.append(event(1)).unwrap();
        drop(spool);
        let mut file = OpenOptions::new()
            .append(true)
            .open(segment_path(dir.path(), 1))
            .unwrap();
        file.write_all(br#"{"idempotency_key":"#).unwrap();
        file.sync_all().unwrap();

        let recovered = AuditSpool::open(config(dir.path().into())).unwrap();
        let drained = recovered.drain_oldest(10);
        assert_eq!(drained.len(), 1);
        assert_eq!(drained[0].1.resource_id, "tool-1");
    }

    #[test]
    fn regression_audit_event_wire_shape_matches_cp_schema() {
        // regression for CAB-2227
        let value = serde_json::to_value(event(1)).unwrap();
        let keys = value
            .as_object()
            .unwrap()
            .keys()
            .cloned()
            .collect::<BTreeSet<_>>();
        assert_eq!(
            keys,
            BTreeSet::from([
                "source".into(),
                "event_type".into(),
                "decision".into(),
                "reason".into(),
                "tenant_id".into(),
                "actor_id".into(),
                "session_id".into(),
                "resource_type".into(),
                "resource_id".into(),
                "tool_call_id".into(),
                "approval_id".into(),
                "policy_version".into(),
                "correlation_id".into(),
                "occurred_at".into(),
                "details".into(),
            ])
        );
        assert_eq!(value["decision"], "deny");
    }
}
