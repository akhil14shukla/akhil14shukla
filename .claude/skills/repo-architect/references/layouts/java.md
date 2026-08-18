# Java / Kotlin layout

The idiomatic tree for a Java or Kotlin service, and why package-by-feature
gives you a real visibility boundary that package-by-layer does not.

```
service/
├── build.gradle.kts  settings.gradle.kts  gradle/libs.versions.toml
├── src/
│   ├── main/
│   │   ├── java/com/company/service/
│   │   │   ├── Application.java
│   │   │   ├── order/            # package per domain, not per layer
│   │   │   │   ├── OrderController.java
│   │   │   │   ├── OrderService.java
│   │   │   │   ├── OrderRepository.java
│   │   │   │   └── Order.java
│   │   │   └── shared/config/  shared/error/
│   │   └── resources/  application.yml  db/migration/
│   └── test/java/com/company/service/order/OrderServiceTest.java
```

Package-by-feature (`order/`) rather than package-by-layer
(`controllers/`, `services/`) gives you package-private visibility as a real
boundary: `OrderRepository` can be package-private and genuinely unreachable from
other features. Use the version catalogue (`libs.versions.toml`) so dependency
versions live in one place.
