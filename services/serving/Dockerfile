# syntax=docker/dockerfile:1
# Multi-stage JVM build for the TarifHub serving service (Quarkus, Java 21).
# For a native binary instead: build with `-Pnative` and swap the runtime stage for
# a minimal base (e.g. quay.io/quarkus/quarkus-micro-image) copying target/*-runner.

# --- build ---
FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /build
# Warm the dependency cache first for faster rebuilds.
COPY pom.xml .
RUN mvn -B -q dependency:go-offline || true
COPY src ./src
RUN mvn -B -q clean package -DskipTests

# --- runtime (Quarkus fast-jar) ---
FROM eclipse-temurin:21-jre AS runtime
ENV LANG=C.UTF-8 \
    JAVA_OPTS="-XX:+UseParallelGC -XX:MaxRAMPercentage=75"
WORKDIR /app

COPY --from=build /build/target/quarkus-app/lib/ /app/lib/
COPY --from=build /build/target/quarkus-app/*.jar /app/
COPY --from=build /build/target/quarkus-app/app/ /app/app/
COPY --from=build /build/target/quarkus-app/quarkus/ /app/quarkus/

USER 1001
EXPOSE 8080
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -jar /app/quarkus-run.jar"]
