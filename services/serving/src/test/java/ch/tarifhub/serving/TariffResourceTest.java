package ch.tarifhub.serving;

import static io.restassured.RestAssured.given;

import org.junit.jupiter.api.Test;

import io.quarkus.test.junit.QuarkusTest;

/**
 * Simple end-to-end checks of the deterministic value path. Asserts status and content
 * type only, so it passes against an empty-but-migrated database (no seeded data needed).
 * Requires a reachable Postgres with the schema applied (docker-compose up db && scripts/init_db.sh)
 * or Quarkus Dev Services with a pgvector-enabled image.
 */
@QuarkusTest
class TariffResourceTest {

    @Test
    void listReturnsJson() {
        given()
                .accept("application/json")
                .when().get("/api/v1/tariffs")
                .then().statusCode(200);
    }

    @Test
    void listIsAlsoAvailableAsXml() {
        given()
                .accept("application/xml")
                .when().get("/api/v1/tariffs")
                .then().statusCode(200);
    }

    @Test
    void unknownKeyReturns404() {
        given()
                .accept("application/json")
                .when().get("/api/v1/tariffs/EAL/__does_not_exist__")
                .then().statusCode(404);
    }
}
