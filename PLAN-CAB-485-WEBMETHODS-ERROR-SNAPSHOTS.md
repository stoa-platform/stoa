# Plan: CAB-485 - Error Snapshots via webMethods Gateway

## Objectif

Capturer les erreurs (4xx/5xx) au niveau de la Gateway webMethods et les publier vers le système Error Snapshots existant via Kafka.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          webMethods Gateway                                  │
│                                                                             │
│  Client Request → Policies → Backend → Response                             │
│                                    │                                        │
│                              (si 4xx/5xx)                                   │
│                                    ▼                                        │
│                        ┌──────────────────────┐                             │
│                        │ ErrorSnapshotPolicy  │                             │
│                        │ (Java Extension)     │                             │
│                        └──────────┬───────────┘                             │
│                                   │                                         │
└───────────────────────────────────┼─────────────────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │  Kafka: stoa.errors.snapshots │
                    │  (Redpanda)                   │
                    └───────────────┬───────────────┘
                                    │
                                    ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│                        Control Plane API                                      │
│                                                                               │
│  ┌────────────────────────┐      ┌─────────────────────┐                     │
│  │ ErrorSnapshotConsumer  │ ──▶  │ SnapshotService     │                     │
│  │ (Kafka Consumer)       │      │ (existing)          │                     │
│  └────────────────────────┘      └──────────┬──────────┘                     │
│                                             │                                 │
│                                             ▼                                 │
│                                  ┌─────────────────────┐                     │
│                                  │ MinIO               │                     │
│                                  │ (error-snapshots)   │                     │
│                                  └─────────────────────┘                     │
└───────────────────────────────────────────────────────────────────────────────┘
```

## Composants

### 1. webMethods Error Snapshot Policy (Java)

**Fichier:** `webmethods-policies/ErrorSnapshotPolicy/`

```
ErrorSnapshotPolicy/
├── src/
│   └── com/stoa/gateway/policy/
│       ├── ErrorSnapshotPolicy.java      # Policy principale
│       ├── SnapshotBuilder.java          # Construction du payload
│       ├── KafkaPublisher.java           # Publication Kafka
│       └── PiiMasker.java                # Masquage PII
├── resources/
│   └── META-INF/
│       └── policy.xml                    # Descriptor policy
├── pom.xml
└── README.md
```

**ErrorSnapshotPolicy.java:**
```java
package com.stoa.gateway.policy;

import com.softwareag.apigateway.extension.*;
import com.softwareag.apigateway.extension.context.*;
import org.apache.kafka.clients.producer.*;

public class ErrorSnapshotPolicy implements Policy {

    private static final String KAFKA_TOPIC = "stoa.errors.snapshots";
    private KafkaPublisher publisher;
    private PiiMasker masker;

    @Override
    public void initialize(PolicyContext context) {
        this.publisher = new KafkaPublisher(
            context.getProperty("kafka.bootstrap.servers"),
            context.getProperty("kafka.sasl.username"),
            context.getProperty("kafka.sasl.password")
        );
        this.masker = new PiiMasker();
    }

    @Override
    public void execute(InvocationContext ctx) throws PolicyException {
        // Only capture on error responses
        int statusCode = ctx.getResponse().getStatusCode();

        if (statusCode >= 400) {
            try {
                ErrorSnapshot snapshot = buildSnapshot(ctx, statusCode);
                publisher.publish(KAFKA_TOPIC, snapshot);
            } catch (Exception e) {
                // Log but don't fail the request
                ctx.getLogger().warn("Failed to capture error snapshot", e);
            }
        }
    }

    private ErrorSnapshot buildSnapshot(InvocationContext ctx, int statusCode) {
        SnapshotBuilder builder = new SnapshotBuilder(masker);

        return builder
            .withTenantId(extractTenantId(ctx))
            .withTrigger(statusCode >= 500 ? "5xx" : "4xx")
            .withRequest(ctx.getRequest())
            .withResponse(ctx.getResponse())
            .withRouting(ctx.getRoutingContext())
            .withPoliciesApplied(ctx.getPoliciesExecuted())
            .withBackendState(ctx.getBackendContext())
            .withTraceId(ctx.getTraceId())
            .withGatewayMetadata()
            .build();
    }

    private String extractTenantId(InvocationContext ctx) {
        // Extract from JWT claims or API context
        String jwt = ctx.getRequest().getHeader("Authorization");
        if (jwt != null && jwt.startsWith("Bearer ")) {
            return JwtUtils.extractClaim(jwt, "tenant_id");
        }
        // Fallback to API's tenant
        return ctx.getApiContext().getTenantId();
    }
}
```

**SnapshotBuilder.java:**
```java
package com.stoa.gateway.policy;

import java.time.Instant;
import java.util.*;

public class SnapshotBuilder {
    private PiiMasker masker;
    private ErrorSnapshot snapshot;
    private List<String> maskedFields = new ArrayList<>();

    public SnapshotBuilder(PiiMasker masker) {
        this.masker = masker;
        this.snapshot = new ErrorSnapshot();
        this.snapshot.setId(generateSnapshotId());
        this.snapshot.setTimestamp(Instant.now());
        this.snapshot.setSource("webmethods-gateway"); // Distinguish from control-plane
    }

    private String generateSnapshotId() {
        // Format: SNP-YYYYMMDD-HHMMSS-xxxxxxxx
        String date = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd-HHmmss"));
        String random = UUID.randomUUID().toString().substring(0, 8);
        return String.format("SNP-%s-%s", date, random);
    }

    public SnapshotBuilder withRequest(GatewayRequest request) {
        RequestSnapshot req = new RequestSnapshot();
        req.setMethod(request.getMethod());
        req.setPath(request.getPath());
        req.setQueryParams(request.getQueryParameters());

        // Mask sensitive headers
        Map<String, String> headers = masker.maskHeaders(request.getHeaders());
        req.setHeaders(headers);
        maskedFields.addAll(masker.getLastMaskedFields());

        // Mask body
        Object body = masker.maskBody(request.getBody());
        req.setBody(body);
        maskedFields.addAll(masker.getLastMaskedFields());

        req.setClientIp(request.getClientIP());
        req.setUserAgent(request.getHeader("User-Agent"));

        snapshot.setRequest(req);
        return this;
    }

    public SnapshotBuilder withResponse(GatewayResponse response) {
        ResponseSnapshot resp = new ResponseSnapshot();
        resp.setStatus(response.getStatusCode());
        resp.setHeaders(masker.maskHeaders(response.getHeaders()));
        resp.setBody(masker.maskBody(response.getBody()));
        resp.setDurationMs(response.getDuration());

        snapshot.setResponse(resp);
        return this;
    }

    public SnapshotBuilder withRouting(RoutingContext routing) {
        RoutingInfo info = new RoutingInfo();
        info.setApiName(routing.getApiName());
        info.setApiVersion(routing.getApiVersion());
        info.setBackendUrl(routing.getBackendUrl());
        info.setEndpoint(routing.getEndpoint());

        snapshot.setRouting(info);
        return this;
    }

    public SnapshotBuilder withPoliciesApplied(List<PolicyExecution> policies) {
        List<PolicyResult> results = policies.stream()
            .map(p -> new PolicyResult(
                p.getName(),
                p.getStatus(),
                p.getDurationMs(),
                p.getMessage()
            ))
            .collect(Collectors.toList());

        snapshot.setPoliciesApplied(results);
        return this;
    }

    public SnapshotBuilder withBackendState(BackendContext backend) {
        BackendState state = new BackendState();
        state.setHealthy(backend.isHealthy());
        state.setLastErrorRate(backend.getErrorRate());
        state.setAvgLatencyMs(backend.getAverageLatency());
        state.setActiveConnections(backend.getActiveConnections());
        state.setCircuitBreakerState(backend.getCircuitBreakerState());

        snapshot.setBackendState(state);
        return this;
    }

    public SnapshotBuilder withGatewayMetadata() {
        EnvironmentInfo env = new EnvironmentInfo();
        env.setPod(System.getenv("HOSTNAME"));
        env.setNode(System.getenv("NODE_NAME"));
        env.setNamespace("stoa-system");
        env.setComponent("webmethods-gateway");

        snapshot.setEnvironment(env);
        return this;
    }

    public ErrorSnapshot build() {
        snapshot.setMaskedFields(maskedFields);
        return snapshot;
    }
}
```

**PiiMasker.java:**
```java
package com.stoa.gateway.policy;

import java.util.*;
import java.util.regex.*;

public class PiiMasker {

    private static final String REDACTED = "[REDACTED]";

    private static final Set<String> SENSITIVE_HEADERS = Set.of(
        "authorization", "x-api-key", "cookie", "x-auth-token",
        "x-access-token", "x-refresh-token", "proxy-authorization"
    );

    private static final Set<String> SENSITIVE_BODY_KEYS = Set.of(
        "password", "secret", "token", "api_key", "apikey",
        "access_token", "refresh_token", "private_key",
        "credit_card", "card_number", "cvv", "ssn", "pin"
    );

    // Patterns for PII in values
    private static final Pattern EMAIL_PATTERN =
        Pattern.compile("[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}");
    private static final Pattern CREDIT_CARD_PATTERN =
        Pattern.compile("\\b(?:\\d{4}[- ]?){3}\\d{4}\\b");
    private static final Pattern SSN_PATTERN =
        Pattern.compile("\\b\\d{3}-\\d{2}-\\d{4}\\b");

    private List<String> lastMaskedFields = new ArrayList<>();

    public Map<String, String> maskHeaders(Map<String, String> headers) {
        lastMaskedFields.clear();
        Map<String, String> masked = new LinkedHashMap<>();

        for (Map.Entry<String, String> entry : headers.entrySet()) {
            String key = entry.getKey();
            String value = entry.getValue();

            if (SENSITIVE_HEADERS.contains(key.toLowerCase())) {
                masked.put(key, REDACTED);
                lastMaskedFields.add("headers." + key);
            } else {
                masked.put(key, value);
            }
        }

        return masked;
    }

    public Object maskBody(Object body) {
        lastMaskedFields.clear();

        if (body == null) {
            return null;
        }

        if (body instanceof Map) {
            return maskMap((Map<String, Object>) body, "body");
        }

        if (body instanceof String) {
            return maskStringValue((String) body, "body");
        }

        return body;
    }

    private Map<String, Object> maskMap(Map<String, Object> map, String path) {
        Map<String, Object> masked = new LinkedHashMap<>();

        for (Map.Entry<String, Object> entry : map.entrySet()) {
            String key = entry.getKey();
            Object value = entry.getValue();
            String fieldPath = path + "." + key;

            if (SENSITIVE_BODY_KEYS.contains(key.toLowerCase())) {
                masked.put(key, REDACTED);
                lastMaskedFields.add(fieldPath);
            } else if (value instanceof Map) {
                masked.put(key, maskMap((Map<String, Object>) value, fieldPath));
            } else if (value instanceof List) {
                masked.put(key, maskList((List<?>) value, fieldPath));
            } else if (value instanceof String) {
                String maskedValue = maskStringValue((String) value, fieldPath);
                masked.put(key, maskedValue);
            } else {
                masked.put(key, value);
            }
        }

        return masked;
    }

    private String maskStringValue(String value, String path) {
        if (EMAIL_PATTERN.matcher(value).find() ||
            CREDIT_CARD_PATTERN.matcher(value).find() ||
            SSN_PATTERN.matcher(value).find()) {
            lastMaskedFields.add(path);
            return REDACTED;
        }
        return value;
    }

    public List<String> getLastMaskedFields() {
        return new ArrayList<>(lastMaskedFields);
    }
}
```

**KafkaPublisher.java:**
```java
package com.stoa.gateway.policy;

import org.apache.kafka.clients.producer.*;
import org.apache.kafka.common.serialization.StringSerializer;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.util.Properties;
import java.util.concurrent.*;

public class KafkaPublisher {

    private final KafkaProducer<String, String> producer;
    private final ObjectMapper objectMapper;
    private final ExecutorService executor;

    public KafkaPublisher(String bootstrapServers, String username, String password) {
        Properties props = new Properties();
        props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrapServers);
        props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());
        props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG, StringSerializer.class.getName());

        // SASL configuration
        props.put("security.protocol", "SASL_PLAINTEXT");
        props.put("sasl.mechanism", "SCRAM-SHA-256");
        props.put("sasl.jaas.config", String.format(
            "org.apache.kafka.common.security.scram.ScramLoginModule required " +
            "username=\"%s\" password=\"%s\";", username, password));

        // Performance tuning
        props.put(ProducerConfig.ACKS_CONFIG, "1");
        props.put(ProducerConfig.BATCH_SIZE_CONFIG, 16384);
        props.put(ProducerConfig.LINGER_MS_CONFIG, 10);
        props.put(ProducerConfig.COMPRESSION_TYPE_CONFIG, "snappy");

        this.producer = new KafkaProducer<>(props);
        this.objectMapper = new ObjectMapper();
        this.objectMapper.findAndRegisterModules(); // For Java 8 date/time
        this.executor = Executors.newSingleThreadExecutor();
    }

    public void publish(String topic, ErrorSnapshot snapshot) {
        // Async publish to not block the request
        executor.submit(() -> {
            try {
                String json = objectMapper.writeValueAsString(snapshot);
                ProducerRecord<String, String> record = new ProducerRecord<>(
                    topic,
                    snapshot.getTenantId(),  // Key for partitioning by tenant
                    json
                );

                producer.send(record, (metadata, exception) -> {
                    if (exception != null) {
                        // Log error but don't fail
                        System.err.println("Failed to publish snapshot: " + exception.getMessage());
                    }
                });
            } catch (Exception e) {
                System.err.println("Failed to serialize snapshot: " + e.getMessage());
            }
        });
    }

    public void close() {
        executor.shutdown();
        producer.close();
    }
}
```

### 2. Kafka Topic Configuration

**Créer le topic `stoa.errors.snapshots`:**

```bash
# Via Redpanda/Kafka
kubectl exec -n stoa-system redpanda-0 -- rpk topic create stoa.errors.snapshots \
  --partitions 6 \
  --replicas 1 \
  --config retention.ms=604800000 \
  --config cleanup.policy=delete
```

### 3. Control Plane Consumer

**Fichier:** `control-plane-api/src/workers/error_snapshot_consumer.py`

```python
"""Kafka consumer for error snapshots from webMethods Gateway.

CAB-485: Consumes error snapshots published by webMethods Gateway
and stores them in MinIO using the existing SnapshotService.
"""

import asyncio
import json
import logging

from aiokafka import AIOKafkaConsumer
from pydantic import ValidationError

from ..config import settings
from ..features.error_snapshots import get_snapshot_service
from ..features.error_snapshots.models import ErrorSnapshot

logger = logging.getLogger(__name__)

TOPIC = "stoa.errors.snapshots"
GROUP_ID = "error-snapshot-consumer"


class ErrorSnapshotConsumer:
    """Kafka consumer for gateway error snapshots."""

    def __init__(self):
        self._consumer: AIOKafkaConsumer | None = None
        self._running = False

    async def start(self) -> None:
        """Start consuming error snapshots from Kafka."""
        self._consumer = AIOKafkaConsumer(
            TOPIC,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id=GROUP_ID,
            auto_offset_reset="earliest",
            enable_auto_commit=True,
            auto_commit_interval_ms=5000,
            value_deserializer=lambda m: json.loads(m.decode("utf-8")),
            # SASL config
            security_protocol="SASL_PLAINTEXT",
            sasl_mechanism="SCRAM-SHA-256",
            sasl_plain_username=settings.KAFKA_SASL_USERNAME,
            sasl_plain_password=settings.KAFKA_SASL_PASSWORD,
        )

        await self._consumer.start()
        self._running = True

        logger.info(
            f"ErrorSnapshotConsumer started, consuming from {TOPIC}"
        )

        try:
            await self._consume_loop()
        finally:
            await self._consumer.stop()

    async def stop(self) -> None:
        """Stop the consumer."""
        self._running = False

    async def _consume_loop(self) -> None:
        """Main consume loop."""
        service = get_snapshot_service()

        if service is None:
            logger.warning(
                "SnapshotService not available, snapshots will be discarded"
            )

        async for message in self._consumer:
            if not self._running:
                break

            try:
                await self._process_message(message, service)
            except Exception as e:
                logger.error(
                    f"Error processing snapshot message: {e}",
                    exc_info=True
                )

    async def _process_message(self, message, service) -> None:
        """Process a single snapshot message."""
        try:
            # Parse and validate the snapshot
            data = message.value

            # Add source metadata
            data["source"] = data.get("source", "webmethods-gateway")

            snapshot = ErrorSnapshot.model_validate(data)

            if service is not None:
                # Store in MinIO using existing service
                await service.storage.save(snapshot)

                logger.info(
                    f"Stored gateway snapshot snapshot_id={snapshot.id} "
                    f"tenant_id={snapshot.tenant_id} status={snapshot.response.status}"
                )
            else:
                logger.debug(
                    f"Discarded snapshot (service unavailable): {snapshot.id}"
                )

        except ValidationError as e:
            logger.warning(
                f"Invalid snapshot format: {e.errors()}"
            )
        except Exception as e:
            logger.error(
                f"Failed to store snapshot: {e}",
                exc_info=True
            )


# Singleton instance
error_snapshot_consumer = ErrorSnapshotConsumer()
```

### 4. Intégration dans main.py

```python
# Dans src/main.py

from .workers.error_snapshot_consumer import error_snapshot_consumer

# Flag pour contrôler le consumer
ENABLE_SNAPSHOT_CONSUMER = os.getenv("ENABLE_SNAPSHOT_CONSUMER", "true").lower() == "true"

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing startup code ...

    # Start error snapshot consumer (CAB-485)
    snapshot_consumer_task = None
    if ENABLE_SNAPSHOT_CONSUMER:
        try:
            snapshot_consumer_task = asyncio.create_task(
                error_snapshot_consumer.start()
            )
            logger.info("Error snapshot consumer started")
        except Exception as e:
            logger.warning("Failed to start error snapshot consumer", error=str(e))

    yield

    # ... existing shutdown code ...

    # Stop error snapshot consumer
    if ENABLE_SNAPSHOT_CONSUMER and snapshot_consumer_task:
        await error_snapshot_consumer.stop()
        snapshot_consumer_task.cancel()
        try:
            await snapshot_consumer_task
        except asyncio.CancelledError:
            pass
```

### 5. Configuration webMethods

**Policy Deployment dans webMethods:**

1. Packager la policy en JAR:
```bash
cd webmethods-policies/ErrorSnapshotPolicy
mvn clean package
```

2. Déployer dans webMethods:
   - Upload `target/error-snapshot-policy-1.0.0.jar` dans Gateway
   - Configurer dans Administration → Extended Settings → Custom Policies

3. Configurer les propriétés:
```properties
# Policy configuration
error.snapshot.policy.enabled=true
error.snapshot.policy.capture.4xx=false
error.snapshot.policy.capture.5xx=true

# Kafka settings
kafka.bootstrap.servers=redpanda.stoa-system:9093
kafka.sasl.username=stoa-gateway
kafka.sasl.password=${KAFKA_SASL_PASSWORD}
```

4. Attacher la policy aux APIs:
   - Global Policy (toutes les APIs)
   - Ou par API individuelle

---

## Schéma de Données

Le schéma `ErrorSnapshot` est **identique** à celui de la Phase 1 (CAB-397), avec un champ additionnel:

```python
class ErrorSnapshot(BaseModel):
    # ... existing fields ...

    # New field to distinguish source
    source: str = "control-plane"  # "control-plane" | "webmethods-gateway"
```

Cela permet:
- Une vue unifiée dans l'UI
- Filtrage par source si nécessaire
- Même format de stockage MinIO

---

## Tests

### Test unitaire Java (Policy)

```java
@Test
public void testSnapshotBuilderMasksSensitiveHeaders() {
    PiiMasker masker = new PiiMasker();
    SnapshotBuilder builder = new SnapshotBuilder(masker);

    Map<String, String> headers = Map.of(
        "Authorization", "Bearer secret-token",
        "Content-Type", "application/json"
    );

    // Mock request with headers
    GatewayRequest request = mockRequest(headers);
    builder.withRequest(request);

    ErrorSnapshot snapshot = builder.build();

    assertEquals("[REDACTED]", snapshot.getRequest().getHeaders().get("Authorization"));
    assertEquals("application/json", snapshot.getRequest().getHeaders().get("Content-Type"));
    assertTrue(snapshot.getMaskedFields().contains("headers.Authorization"));
}
```

### Test d'intégration (Consumer Python)

```python
@pytest.mark.asyncio
async def test_consumer_stores_gateway_snapshot():
    """Test that gateway snapshots are stored correctly."""
    # Create test snapshot message
    snapshot_data = {
        "id": "SNP-20260115-100000-test1234",
        "timestamp": "2026-01-15T10:00:00Z",
        "tenant_id": "tenant-test",
        "source": "webmethods-gateway",
        "trigger": "5xx",
        "request": {
            "method": "POST",
            "path": "/api/v1/orders",
            "headers": {"Content-Type": "application/json"},
            "body": {"order_id": "123"},
        },
        "response": {
            "status": 500,
            "headers": {},
            "body": {"error": "Internal Server Error"},
            "duration_ms": 150,
        },
        # ... other required fields
    }

    # Process message
    consumer = ErrorSnapshotConsumer()
    await consumer._process_message(
        MockMessage(value=snapshot_data),
        mock_service
    )

    # Verify storage was called
    mock_service.storage.save.assert_called_once()
    saved_snapshot = mock_service.storage.save.call_args[0][0]
    assert saved_snapshot.source == "webmethods-gateway"
    assert saved_snapshot.id == "SNP-20260115-100000-test1234"
```

---

## Métriques Prometheus

### webMethods (Java)
```java
// Ajouter dans ErrorSnapshotPolicy
private final Counter snapshotsPublished = Counter.build()
    .name("gateway_error_snapshots_published_total")
    .help("Total error snapshots published to Kafka")
    .labelNames("trigger", "tenant_id")
    .register();

private final Counter snapshotPublishErrors = Counter.build()
    .name("gateway_error_snapshots_publish_errors_total")
    .help("Failed snapshot publications")
    .register();
```

### Control Plane (Python)
```python
# Dans error_snapshot_consumer.py
from prometheus_client import Counter, Histogram

SNAPSHOTS_CONSUMED = Counter(
    "error_snapshots_consumed_total",
    "Total snapshots consumed from Kafka",
    ["source", "trigger"]
)

SNAPSHOTS_STORED = Counter(
    "error_snapshots_stored_total",
    "Total snapshots stored in MinIO",
    ["source"]
)

SNAPSHOT_PROCESS_DURATION = Histogram(
    "error_snapshot_process_duration_seconds",
    "Time to process and store a snapshot"
)
```

---

## Ordre d'Implémentation

1. **Kafka Topic** - Créer `stoa.errors.snapshots`
2. **Consumer Python** - `error_snapshot_consumer.py`
3. **Intégration main.py** - Démarrer le consumer
4. **Policy Java** - Développer ErrorSnapshotPolicy
5. **Deployment webMethods** - Configurer et attacher la policy
6. **Tests** - E2E avec erreur réelle
7. **Dashboards** - Ajouter filtrage par source

---

## Variables d'Environnement

### Control Plane
```yaml
ENABLE_SNAPSHOT_CONSUMER: "true"
# Kafka settings already exist
```

### webMethods Gateway
```yaml
STOA_SNAPSHOT_POLICY_ENABLED: "true"
STOA_SNAPSHOT_CAPTURE_4XX: "false"
STOA_SNAPSHOT_CAPTURE_5XX: "true"
KAFKA_BOOTSTRAP_SERVERS: "redpanda.stoa-system:9093"
KAFKA_SASL_USERNAME: "stoa-gateway"
KAFKA_SASL_PASSWORD: "${secret}"
```

---

## Avantages de cette Architecture

1. **Découplage** - Gateway publie, Control Plane consomme
2. **Résilience** - Kafka bufferise si le consumer est down
3. **Scalabilité** - Multiple consumers possibles
4. **Uniformité** - Même schéma, même stockage
5. **Visibilité** - Erreurs des 2 sources dans une seule UI
