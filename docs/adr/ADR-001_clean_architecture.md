# ADR-001: Clean (Hexagonal) Architecture for Target Domain Service

**Status:** Accepted  
**Date:** 2026-10-28  
**Author:** Staff AI Systems Engineer  
**Classification:** Financial Enterprise Grade (Schwab Internal Standard Compliance)  

---

## 1. Context & Problem Statement
The URL Shortener service must handle high-volume redirects with sub-10ms P95 latency while adhering to financial enterprise security, compliance, and maintainability standards. In traditional layered or monolithic frameworks (e.g. Django, standard FastAPI scaffolding), business rules frequently get entangled with HTTP transport logic, ORM database models, and external caching libraries. This creates tight coupling, makes unit testing slow, and drastically increases the risk of regression during agentic code modifications.

## 2. Decision
We adopt **Clean Architecture / Hexagonal Architecture (Ports and Adapters)** with strict unidirectional dependency boundaries:

1. **Domain Layer (`src/url_shortener/domain/`):**
   - Contains pure business logic, entities (`ShortenedUrl`, `ClickEvent`), value objects (`ShortCode`, `OriginalUrl`), domain exceptions, and abstract ports (`UrlRepository`, `AnalyticsRepository`, `CacheService`, `RateLimiterService`).
   - Zero external framework dependencies; pure standard library.
2. **Application Layer (`src/url_shortener/application/`):**
   - Coordinates domain aggregates via Use Cases (`CreateShortUrlUseCase`, `ResolveRedirectUseCase`, `GetAnalyticsUseCase`).
   - Uses immutable Data Transfer Objects (DTOs) for request/response contracts.
3. **Infrastructure Layer (`src/url_shortener/infrastructure/`):**
   - Implements ports with concrete database adapters (SQLAlchemy ORM + SQLite/Postgres), caching (Redis with transparent in-memory fallback), security validators (SSRF IP parser), and Base62 Snowflake encoders.
4. **Presentation Layer (`src/url_shortener/presentation/`):**
   - FastAPI REST API controllers, OpenAPI 3.1 schemas, exception handlers, and security/rate-limiting middleware.

## 3. Invariants & Rules Enforced
- **Dependency Rule:** Inner layers must never import or depend on outer layers. Domain cannot import from `infrastructure` or `presentation`.
- **AST Enforced:** The orchestrator's [`GovernancePolicyEngine`](file:///Users/niharikapasham/Documents/workspace/url-shortener/src/orchestrator/governance.py) statically checks AST imports in `src/url_shortener/domain/` to guarantee that outer modules are never imported.

## 4. Consequences & Trade-offs
### Positive:
- **Testability:** Domain logic and use cases can be tested instantaneously with in-memory adapters (43 tests run in $< 0.8\text{ s}$).
- **Flexibility:** Swapping storage (SQLite to Postgres) or cache (in-memory to Redis) requires zero changes to core business rules.
- **Agent Safety:** High-risk refactoring by autonomous agents is constrained; blast radius is easily isolated.

### Negative / Mitigations:
- **Code Volume:** Requires explicit DTOs and repository ports. Mitigated by automated scaffolding and strict type hinting.

