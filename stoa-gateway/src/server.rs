//! HTTP server loop with connection-level limits.
//!
//! Replaces `axum::serve`, which applies no idle or header-read deadline and
//! no bound on concurrent connections. Each accepted connection is served by
//! hyper (HTTP/1.1 and HTTP/2, with upgrades for WebSocket) and watched by a
//! small per-connection supervisor that enforces:
//!
//! - **Idle timeout**: a connection with no in-flight request and no I/O for
//!   `idle_timeout` is shut down gracefully (keep-alive and never-used
//!   connections alike). In-flight requests and streaming responses are never
//!   interrupted by this deadline.
//! - **Header read timeout** (HTTP/1): once the first byte of a new request
//!   arrives, the request head must be fully received within
//!   `header_read_timeout`, otherwise the connection is closed.
//! - **Connection cap**: at most `max_connections` connections are served at
//!   once. Connections accepted beyond the cap are closed immediately.
//!
//! Graceful shutdown matches the previous behaviour: on the shutdown signal the
//! listener stops accepting, every connection is asked to shut down gracefully,
//! and the server returns once all connection tasks have finished.

use std::convert::Infallible;
use std::future::Future;
use std::io;
use std::net::SocketAddr;
use std::pin::Pin;
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::sync::Arc;
use std::task::{Context, Poll};
use std::time::Duration;

use axum::body::Body;
use axum::body::Bytes;
use axum::extract::ConnectInfo;
use axum::Router;
use hyper::body::Incoming;
use hyper::Request;
use hyper_util::rt::{TokioExecutor, TokioIo};
use hyper_util::server::conn::auto::Builder;
use once_cell::sync::Lazy;
use prometheus::{
    register_int_counter, register_int_counter_vec, register_int_gauge, IntCounter, IntCounterVec,
    IntGauge,
};
use tokio::io::{AsyncRead, AsyncWrite, ReadBuf};
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::{watch, Notify, Semaphore};
use tokio::time::Instant;
use tower::ServiceExt;
use tracing::{debug, error, trace, warn};

/// Default idle timeout for client connections (seconds).
pub const DEFAULT_IDLE_TIMEOUT_SECS: u64 = 60;
/// Default HTTP/1 request header read timeout (seconds).
pub const DEFAULT_HEADER_READ_TIMEOUT_SECS: u64 = 10;
/// Default maximum number of concurrent client connections.
pub const DEFAULT_MAX_CONNECTIONS: usize = 4096;

/// Prometheus gauge: client connections currently being served.
pub static HTTP_CONNECTIONS_ACTIVE: Lazy<IntGauge> = Lazy::new(|| {
    register_int_gauge!(
        "gateway_http_connections_active",
        "Client HTTP connections currently open"
    )
    .expect("Failed to create gateway_http_connections_active metric")
});

/// Prometheus gauge: configured connection cap (0 = unlimited).
pub static HTTP_CONNECTIONS_MAX: Lazy<IntGauge> = Lazy::new(|| {
    register_int_gauge!(
        "gateway_http_connections_max",
        "Configured maximum of concurrent client HTTP connections (0 = unlimited)"
    )
    .expect("Failed to create gateway_http_connections_max metric")
});

/// Prometheus counter: connections closed at accept because the cap was reached.
pub static HTTP_CONNECTIONS_REJECTED_TOTAL: Lazy<IntCounter> = Lazy::new(|| {
    register_int_counter!(
        "gateway_http_connections_rejected_total",
        "Client HTTP connections closed at accept because the connection cap was reached"
    )
    .expect("Failed to create gateway_http_connections_rejected_total metric")
});

/// Prometheus counter: connections closed by the server-side deadlines.
pub static HTTP_CONNECTIONS_TIMED_OUT_TOTAL: Lazy<IntCounterVec> = Lazy::new(|| {
    register_int_counter_vec!(
        "gateway_http_connections_timed_out_total",
        "Client HTTP connections closed by a server-side deadline",
        &["reason"]
    )
    .expect("Failed to create gateway_http_connections_timed_out_total metric")
});

/// Force registration of the server metrics (so they show up before traffic).
pub fn init_metrics() {
    Lazy::force(&HTTP_CONNECTIONS_ACTIVE);
    Lazy::force(&HTTP_CONNECTIONS_MAX);
    Lazy::force(&HTTP_CONNECTIONS_REJECTED_TOTAL);
    Lazy::force(&HTTP_CONNECTIONS_TIMED_OUT_TOTAL);
}

/// Connection-level limits applied by [`serve`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ServerLimits {
    /// Close connections idle for this long. `None` disables the deadline.
    pub idle_timeout: Option<Duration>,
    /// Close HTTP/1 connections that do not finish sending a request head
    /// within this long. `None` disables the deadline.
    pub header_read_timeout: Option<Duration>,
    /// Maximum concurrent connections. `None` means unlimited.
    pub max_connections: Option<usize>,
}

impl Default for ServerLimits {
    fn default() -> Self {
        Self {
            idle_timeout: Some(Duration::from_secs(DEFAULT_IDLE_TIMEOUT_SECS)),
            header_read_timeout: Some(Duration::from_secs(DEFAULT_HEADER_READ_TIMEOUT_SECS)),
            max_connections: Some(DEFAULT_MAX_CONNECTIONS),
        }
    }
}

impl ServerLimits {
    /// Build limits from config values where `0` disables the corresponding limit.
    pub fn from_config_values(
        idle_timeout_secs: u64,
        header_read_timeout_secs: u64,
        max_connections: usize,
    ) -> Self {
        let secs = |v: u64| (v > 0).then(|| Duration::from_secs(v));
        Self {
            idle_timeout: secs(idle_timeout_secs),
            header_read_timeout: secs(header_read_timeout_secs),
            max_connections: (max_connections > 0).then_some(max_connections),
        }
    }
}

/// Serve `app` on `listener` until `signal` resolves, then drain gracefully.
///
/// Requests carry `ConnectInfo<SocketAddr>` like
/// `into_make_service_with_connect_info::<SocketAddr>()`.
pub async fn serve<F>(
    listener: TcpListener,
    app: Router,
    limits: ServerLimits,
    signal: F,
) -> io::Result<()>
where
    F: Future<Output = ()> + Send + 'static,
{
    HTTP_CONNECTIONS_MAX.set(limits.max_connections.unwrap_or(0) as i64);
    let permits = limits.max_connections.map(|n| Arc::new(Semaphore::new(n)));

    // Dropping `signal_rx` tells every connection task to shut down gracefully.
    let (signal_tx, signal_rx) = watch::channel(());
    let signal_tx = Arc::new(signal_tx);
    tokio::spawn(async move {
        signal.await;
        drop(signal_rx);
    });
    // Each connection task holds a `close_rx`; `close_tx.closed()` resolves once all are gone.
    let (close_tx, close_rx) = watch::channel(());

    loop {
        let (stream, remote) = tokio::select! {
            accepted = accept(&listener) => match accepted {
                Some(conn) => conn,
                None => continue,
            },
            _ = signal_tx.closed() => break,
        };

        let permit = match &permits {
            Some(sem) => match sem.clone().try_acquire_owned() {
                Ok(permit) => Some(permit),
                Err(_) => {
                    HTTP_CONNECTIONS_REJECTED_TOTAL.inc();
                    debug!(%remote, "connection cap reached, closing new connection");
                    drop(stream);
                    continue;
                }
            },
            None => None,
        };

        if let Err(err) = stream.set_nodelay(true) {
            trace!("failed to set TCP_NODELAY: {err}");
        }

        let app = app.clone();
        let signal_tx = Arc::clone(&signal_tx);
        let close_rx = close_rx.clone();
        tokio::spawn(async move {
            let _active = ActiveGuard::new();
            serve_connection(stream, remote, app, limits, signal_tx).await;
            drop(permit);
            drop(close_rx);
        });
    }

    drop(close_rx);
    drop(listener);
    close_tx.closed().await;
    Ok(())
}

async fn accept(listener: &TcpListener) -> Option<(TcpStream, SocketAddr)> {
    match listener.accept().await {
        Ok(conn) => Some(conn),
        Err(e) => {
            if matches!(
                e.kind(),
                io::ErrorKind::ConnectionRefused
                    | io::ErrorKind::ConnectionAborted
                    | io::ErrorKind::ConnectionReset
            ) {
                return None;
            }
            // e.g. EMFILE: back off instead of spinning (same as axum::serve).
            error!("accept error: {e}");
            tokio::time::sleep(Duration::from_secs(1)).await;
            None
        }
    }
}

struct ActiveGuard;

impl ActiveGuard {
    fn new() -> Self {
        HTTP_CONNECTIONS_ACTIVE.inc();
        Self
    }
}

impl Drop for ActiveGuard {
    fn drop(&mut self) {
        HTTP_CONNECTIONS_ACTIVE.dec();
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Expired {
    Idle,
    HeaderRead,
}

const NO_HEADER: u64 = u64::MAX;

/// Per-connection activity shared by the I/O wrapper, the service and the supervisor.
struct Activity {
    base: Instant,
    inflight: AtomicUsize,
    /// Milliseconds since `base` of the last byte read or written.
    last_io_ms: AtomicU64,
    /// Milliseconds since `base` when a new request head started, or `NO_HEADER`.
    header_started_ms: AtomicU64,
    /// Set once the client speaks HTTP/2 (header read deadline does not apply).
    h2: AtomicBool,
    first_read_done: AtomicBool,
    notify: Notify,
}

impl Activity {
    fn new() -> Self {
        Self {
            base: Instant::now(),
            inflight: AtomicUsize::new(0),
            last_io_ms: AtomicU64::new(0),
            header_started_ms: AtomicU64::new(NO_HEADER),
            h2: AtomicBool::new(false),
            first_read_done: AtomicBool::new(false),
            notify: Notify::new(),
        }
    }

    fn now_ms(&self) -> u64 {
        self.base.elapsed().as_millis() as u64
    }

    fn on_read(&self, data: &[u8]) {
        if data.is_empty() {
            return;
        }
        let now = self.now_ms();
        self.last_io_ms.store(now, Ordering::Relaxed);
        if !self.first_read_done.swap(true, Ordering::Relaxed) && data.starts_with(b"PRI * HTTP/2")
        {
            self.h2.store(true, Ordering::Relaxed);
        }
        if self.h2.load(Ordering::Relaxed) || self.inflight.load(Ordering::Acquire) > 0 {
            return;
        }
        if self
            .header_started_ms
            .compare_exchange(NO_HEADER, now, Ordering::AcqRel, Ordering::Relaxed)
            .is_ok()
        {
            self.notify.notify_one();
        }
    }

    fn on_write(&self) {
        self.last_io_ms.store(self.now_ms(), Ordering::Relaxed);
    }

    fn request_started(&self) {
        self.inflight.fetch_add(1, Ordering::AcqRel);
        self.header_started_ms.store(NO_HEADER, Ordering::Release);
    }

    fn request_finished(&self) {
        self.last_io_ms.store(self.now_ms(), Ordering::Relaxed);
        if self.inflight.fetch_sub(1, Ordering::AcqRel) == 1 {
            self.notify.notify_one();
        }
    }

    /// Next instant at which a deadline may expire, if any applies right now.
    fn next_deadline(&self, limits: &ServerLimits) -> Option<Instant> {
        if self.inflight.load(Ordering::Acquire) > 0 {
            return None;
        }
        let header = self.header_started_ms.load(Ordering::Acquire);
        let at = |ms: u64, d: Duration| self.base + Duration::from_millis(ms) + d;
        if header != NO_HEADER {
            // A request head is being received: only the header deadline applies.
            return limits.header_read_timeout.map(|d| at(header, d));
        }
        limits
            .idle_timeout
            .map(|d| at(self.last_io_ms.load(Ordering::Relaxed), d))
    }

    fn expired(&self, limits: &ServerLimits) -> Option<Expired> {
        if self.inflight.load(Ordering::Acquire) > 0 {
            return None;
        }
        let now = self.now_ms();
        let header = self.header_started_ms.load(Ordering::Acquire);
        if header != NO_HEADER {
            return match limits.header_read_timeout {
                Some(d) if now.saturating_sub(header) >= d.as_millis() as u64 => {
                    Some(Expired::HeaderRead)
                }
                _ => None,
            };
        }
        match limits.idle_timeout {
            Some(d)
                if now.saturating_sub(self.last_io_ms.load(Ordering::Relaxed))
                    >= d.as_millis() as u64 =>
            {
                Some(Expired::Idle)
            }
            _ => None,
        }
    }
}

/// Decrements the in-flight count when the response body is done (or dropped).
struct InflightGuard(Arc<Activity>);

impl InflightGuard {
    fn new(activity: Arc<Activity>) -> Self {
        activity.request_started();
        Self(activity)
    }
}

impl Drop for InflightGuard {
    fn drop(&mut self) {
        self.0.request_finished();
    }
}

/// Response body that keeps the request counted as in flight until it is fully sent.
struct TrackedBody {
    inner: Body,
    _guard: InflightGuard,
}

impl http_body::Body for TrackedBody {
    type Data = Bytes;
    type Error = axum::Error;

    fn poll_frame(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
    ) -> Poll<Option<Result<http_body::Frame<Self::Data>, Self::Error>>> {
        Pin::new(&mut self.inner).poll_frame(cx)
    }

    fn is_end_stream(&self) -> bool {
        self.inner.is_end_stream()
    }

    fn size_hint(&self) -> http_body::SizeHint {
        self.inner.size_hint()
    }
}

/// TCP stream wrapper recording read/write activity.
struct TrackedIo {
    inner: TcpStream,
    activity: Arc<Activity>,
}

impl AsyncRead for TrackedIo {
    fn poll_read(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buf: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        let before = buf.filled().len();
        let res = Pin::new(&mut self.inner).poll_read(cx, buf);
        if let Poll::Ready(Ok(())) = res {
            self.activity.on_read(&buf.filled()[before..]);
        }
        res
    }
}

impl AsyncWrite for TrackedIo {
    fn poll_write(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buf: &[u8],
    ) -> Poll<io::Result<usize>> {
        let res = Pin::new(&mut self.inner).poll_write(cx, buf);
        if let Poll::Ready(Ok(n)) = res {
            if n > 0 {
                self.activity.on_write();
            }
        }
        res
    }

    fn poll_write_vectored(
        mut self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        bufs: &[io::IoSlice<'_>],
    ) -> Poll<io::Result<usize>> {
        let res = Pin::new(&mut self.inner).poll_write_vectored(cx, bufs);
        if let Poll::Ready(Ok(n)) = res {
            if n > 0 {
                self.activity.on_write();
            }
        }
        res
    }

    fn is_write_vectored(&self) -> bool {
        self.inner.is_write_vectored()
    }

    fn poll_flush(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.inner).poll_flush(cx)
    }

    fn poll_shutdown(mut self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.inner).poll_shutdown(cx)
    }
}

async fn serve_connection(
    stream: TcpStream,
    remote: SocketAddr,
    app: Router,
    limits: ServerLimits,
    signal_tx: Arc<watch::Sender<()>>,
) {
    let activity = Arc::new(Activity::new());
    let io = TokioIo::new(TrackedIo {
        inner: stream,
        activity: activity.clone(),
    });

    let svc_activity = activity.clone();
    let service = hyper::service::service_fn(move |req: Request<Incoming>| {
        let guard = InflightGuard::new(svc_activity.clone());
        let mut req = req.map(Body::new);
        req.extensions_mut().insert(ConnectInfo(remote));
        let app = app.clone();
        async move {
            let resp = app.oneshot(req).await.unwrap_or_else(|err| match err {});
            Ok::<_, Infallible>(resp.map(|inner| {
                Body::new(TrackedBody {
                    inner,
                    _guard: guard,
                })
            }))
        }
    });

    let builder = Builder::new(TokioExecutor::new());
    let conn = builder.serve_connection_with_upgrades(io, service);
    tokio::pin!(conn);

    let signal_closed = signal_tx.closed();
    tokio::pin!(signal_closed);
    let mut shutting_down = false;

    loop {
        let deadline = if shutting_down {
            None
        } else {
            activity.next_deadline(&limits)
        };
        tokio::select! {
            result = conn.as_mut() => {
                if let Err(err) = result {
                    trace!(%remote, "connection error: {err:#}");
                }
                break;
            }
            _ = &mut signal_closed, if !shutting_down => {
                conn.as_mut().graceful_shutdown();
                shutting_down = true;
            }
            _ = activity.notify.notified(), if !shutting_down => {
                // In-flight count or header state changed: recompute the deadline.
            }
            _ = sleep_until_opt(deadline), if deadline.is_some() => {
                match activity.expired(&limits) {
                    Some(Expired::Idle) => {
                        HTTP_CONNECTIONS_TIMED_OUT_TOTAL.with_label_values(&["idle"]).inc();
                        trace!(%remote, "closing idle connection");
                        conn.as_mut().graceful_shutdown();
                        shutting_down = true;
                    }
                    Some(Expired::HeaderRead) => {
                        HTTP_CONNECTIONS_TIMED_OUT_TOTAL
                            .with_label_values(&["header_read"])
                            .inc();
                        warn!(%remote, "request header not received in time, closing connection");
                        break;
                    }
                    None => {}
                }
            }
        }
    }
}

async fn sleep_until_opt(deadline: Option<Instant>) {
    match deadline {
        Some(at) => tokio::time::sleep_until(at).await,
        None => std::future::pending().await,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::routing::get;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    struct TestServer {
        addr: SocketAddr,
        stop: Option<tokio::sync::oneshot::Sender<()>>,
        handle: tokio::task::JoinHandle<io::Result<()>>,
    }

    impl TestServer {
        async fn start(limits: ServerLimits) -> Self {
            let app =
                Router::new().route("/", get(|| async { "ok" })).route(
                    "/peer",
                    get(|ConnectInfo(peer): ConnectInfo<SocketAddr>| async move {
                        peer.ip().to_string()
                    }),
                );
            let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
            let addr = listener.local_addr().unwrap();
            let (tx, rx) = tokio::sync::oneshot::channel::<()>();
            let handle = tokio::spawn(serve(listener, app, limits, async move {
                let _ = rx.await;
            }));
            Self {
                addr,
                stop: Some(tx),
                handle,
            }
        }

        async fn shutdown(mut self) {
            let _ = self.stop.take().unwrap().send(());
            tokio::time::timeout(Duration::from_secs(5), self.handle)
                .await
                .expect("server drains on shutdown")
                .unwrap()
                .unwrap();
        }
    }

    fn limits(idle_ms: u64, header_ms: u64, max: Option<usize>) -> ServerLimits {
        ServerLimits {
            idle_timeout: Some(Duration::from_millis(idle_ms)),
            header_read_timeout: Some(Duration::from_millis(header_ms)),
            max_connections: max,
        }
    }

    /// Send one keep-alive request and read the full response head + body.
    async fn request(stream: &mut TcpStream, path: &str) -> String {
        stream
            .write_all(format!("GET {path} HTTP/1.1\r\nHost: t\r\n\r\n").as_bytes())
            .await
            .unwrap();
        let mut buf = vec![0u8; 4096];
        let mut out = Vec::new();
        loop {
            let n = tokio::time::timeout(Duration::from_secs(5), stream.read(&mut buf))
                .await
                .expect("response in time")
                .unwrap();
            assert!(n > 0, "connection closed before response");
            out.extend_from_slice(&buf[..n]);
            let text = String::from_utf8_lossy(&out);
            if let Some(idx) = text.find("\r\n\r\n") {
                let len = text
                    .lines()
                    .find_map(|l| {
                        l.to_ascii_lowercase()
                            .strip_prefix("content-length: ")
                            .map(|v| v.trim().parse::<usize>().unwrap())
                    })
                    .unwrap_or(0);
                if out.len() >= idx + 4 + len {
                    return text.into_owned();
                }
            }
        }
    }

    /// Wait until the peer closes the connection; returns the elapsed time.
    async fn wait_closed(stream: &mut TcpStream, within: Duration) -> Duration {
        let start = std::time::Instant::now();
        let mut buf = [0u8; 64];
        loop {
            match tokio::time::timeout(within, stream.read(&mut buf)).await {
                Ok(Ok(0)) | Ok(Err(_)) => return start.elapsed(),
                Ok(Ok(_)) => continue,
                Err(_) => panic!("connection still open after {within:?}"),
            }
        }
    }

    #[tokio::test]
    async fn regression_idle_keepalive_connection_is_closed() {
        let server = TestServer::start(limits(300, 5_000, None)).await;
        let mut stream = TcpStream::connect(server.addr).await.unwrap();
        let resp = request(&mut stream, "/").await;
        assert!(resp.starts_with("HTTP/1.1 200"), "{resp}");
        // Connection is reusable before the idle deadline.
        let resp = request(&mut stream, "/").await;
        assert!(resp.starts_with("HTTP/1.1 200"), "{resp}");
        let elapsed = wait_closed(&mut stream, Duration::from_secs(3)).await;
        assert!(
            elapsed >= Duration::from_millis(200),
            "closed too early: {elapsed:?}"
        );
        server.shutdown().await;
    }

    #[tokio::test]
    async fn regression_idle_unused_connection_is_closed() {
        let server = TestServer::start(limits(300, 5_000, None)).await;
        let mut stream = TcpStream::connect(server.addr).await.unwrap();
        wait_closed(&mut stream, Duration::from_secs(3)).await;
        server.shutdown().await;
    }

    #[tokio::test]
    async fn regression_header_read_timeout_closes_partial_request() {
        // Idle deadline far away: only the header deadline can close this connection.
        let server = TestServer::start(limits(30_000, 300, None)).await;
        let mut stream = TcpStream::connect(server.addr).await.unwrap();
        stream.write_all(b"GET / HTTP/1.1\r\nHost:").await.unwrap();
        let elapsed = wait_closed(&mut stream, Duration::from_secs(3)).await;
        assert!(
            elapsed >= Duration::from_millis(200),
            "closed too early: {elapsed:?}"
        );
        server.shutdown().await;
    }

    #[tokio::test]
    async fn regression_header_read_timeout_does_not_cut_keepalive_reuse() {
        // Keep-alive reuse within the idle window works even past the header deadline.
        let server = TestServer::start(limits(5_000, 200, None)).await;
        let mut stream = TcpStream::connect(server.addr).await.unwrap();
        assert!(request(&mut stream, "/").await.starts_with("HTTP/1.1 200"));
        tokio::time::sleep(Duration::from_millis(500)).await;
        assert!(request(&mut stream, "/").await.starts_with("HTTP/1.1 200"));
        server.shutdown().await;
    }

    #[tokio::test]
    async fn regression_connection_cap_is_enforced() {
        let server = TestServer::start(limits(30_000, 30_000, Some(2))).await;
        let rejected_before = HTTP_CONNECTIONS_REJECTED_TOTAL.get();

        let mut a = TcpStream::connect(server.addr).await.unwrap();
        let mut b = TcpStream::connect(server.addr).await.unwrap();
        assert!(request(&mut a, "/").await.starts_with("HTTP/1.1 200"));
        assert!(request(&mut b, "/").await.starts_with("HTTP/1.1 200"));

        // Third concurrent connection is closed without being served.
        let mut c = TcpStream::connect(server.addr).await.unwrap();
        let _ = c.write_all(b"GET / HTTP/1.1\r\nHost: t\r\n\r\n").await;
        let mut buf = [0u8; 64];
        let n = tokio::time::timeout(Duration::from_secs(3), c.read(&mut buf))
            .await
            .expect("over-cap connection is closed promptly")
            .unwrap_or(0);
        assert_eq!(n, 0, "over-cap connection must not be served");
        assert!(HTTP_CONNECTIONS_REJECTED_TOTAL.get() > rejected_before);

        // Releasing a slot lets a new connection in.
        drop(a);
        let mut served = false;
        for _ in 0..50 {
            tokio::time::sleep(Duration::from_millis(20)).await;
            let mut d = TcpStream::connect(server.addr).await.unwrap();
            if d.write_all(b"GET / HTTP/1.1\r\nHost: t\r\nConnection: close\r\n\r\n")
                .await
                .is_err()
            {
                continue;
            }
            let mut out = Vec::new();
            let _ = tokio::time::timeout(Duration::from_secs(2), d.read_to_end(&mut out)).await;
            if out.starts_with(b"HTTP/1.1 200") {
                served = true;
                break;
            }
        }
        assert!(served, "slot freed by a closed connection is reusable");
        drop(b);
        server.shutdown().await;
    }

    #[tokio::test]
    async fn regression_connect_info_is_available_to_handlers() {
        let server = TestServer::start(ServerLimits::default()).await;
        let mut stream = TcpStream::connect(server.addr).await.unwrap();
        let resp = request(&mut stream, "/peer").await;
        assert!(resp.ends_with("127.0.0.1"), "{resp}");
        drop(stream);
        server.shutdown().await;
    }

    #[tokio::test]
    async fn regression_graceful_shutdown_closes_idle_connections() {
        let server = TestServer::start(ServerLimits::default()).await;
        let mut stream = TcpStream::connect(server.addr).await.unwrap();
        assert!(request(&mut stream, "/").await.starts_with("HTTP/1.1 200"));
        // Shutdown completes even though a keep-alive connection is still open.
        server.shutdown().await;
        wait_closed(&mut stream, Duration::from_secs(3)).await;
    }

    #[tokio::test]
    async fn regression_websocket_upgrade_still_works() {
        use axum::extract::ws::{Message, WebSocketUpgrade};
        use futures::{SinkExt, StreamExt};

        let app = Router::new().route(
            "/ws",
            get(|ws: WebSocketUpgrade| async move {
                ws.on_upgrade(|mut socket| async move {
                    while let Some(Ok(msg)) = socket.recv().await {
                        if let Message::Text(t) = msg {
                            let _ = socket.send(Message::Text(t)).await;
                        }
                    }
                })
            }),
        );
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = listener.local_addr().unwrap();
        let (tx, rx) = tokio::sync::oneshot::channel::<()>();
        let handle = tokio::spawn(serve(listener, app, ServerLimits::default(), async move {
            let _ = rx.await;
        }));

        let (mut ws, _) = tokio_tungstenite::connect_async(format!("ws://{addr}/ws"))
            .await
            .expect("websocket handshake");
        ws.send(tokio_tungstenite::tungstenite::Message::Text("ping".into()))
            .await
            .unwrap();
        let reply = tokio::time::timeout(Duration::from_secs(5), ws.next())
            .await
            .unwrap()
            .unwrap()
            .unwrap();
        assert_eq!(reply.into_text().unwrap().as_str(), "ping");
        ws.close(None).await.unwrap();

        let _ = tx.send(());
        tokio::time::timeout(Duration::from_secs(5), handle)
            .await
            .unwrap()
            .unwrap()
            .unwrap();
    }

    #[test]
    fn server_limits_from_config_zero_disables() {
        let l = ServerLimits::from_config_values(0, 0, 0);
        assert_eq!(l.idle_timeout, None);
        assert_eq!(l.header_read_timeout, None);
        assert_eq!(l.max_connections, None);
        let d = ServerLimits::from_config_values(60, 10, 4096);
        assert_eq!(d, ServerLimits::default());
    }
}
