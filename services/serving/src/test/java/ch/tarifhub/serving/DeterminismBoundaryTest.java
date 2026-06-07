package ch.tarifhub.serving;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;

/**
 * Architectural guard (ArchUnit-style, dependency-free): the AI boundary holds in serving.
 *
 * <ol>
 *   <li>Only the {@code ch.tarifhub.serving.search} package may reference langchain4j.</li>
 *   <li>The value path ({@link TariffResource}) imports no LLM client and returns persisted
 *       records read through {@link TariffRepository} / {@link TariffRecordEntity}.</li>
 * </ol>
 *
 * Plain JUnit (not {@code @QuarkusTest}) so it runs without a database.
 */
class DeterminismBoundaryTest {

    private static final Path SRC = Path.of("src", "main", "java");

    @Test
    void onlySearchPackageReferencesLangchain4j() throws IOException {
        List<String> offenders = new ArrayList<>();
        try (Stream<Path> files = Files.walk(SRC)) {
            List<Path> javaFiles = files
                    .filter(Files::isRegularFile)
                    .filter(p -> p.toString().endsWith(".java"))
                    .toList();
            for (Path p : javaFiles) {
                String content = Files.readString(p);
                boolean referencesLangchain4j = content.contains("langchain4j");
                boolean inSearchPackage = p.toString().replace('\\', '/').contains("/serving/search/");
                if (referencesLangchain4j && !inSearchPackage) {
                    offenders.add(p.toString());
                }
            }
        }
        assertTrue(offenders.isEmpty(),
                "langchain4j referenced outside the search package: " + offenders);
    }

    @Test
    void valuePathReturnsPersistedRecordsWithoutAi() throws IOException {
        String resource = Files.readString(SRC.resolve("ch/tarifhub/serving/TariffResource.java"));
        assertFalse(resource.contains("langchain4j"), "the value path must not import an LLM client");
        assertTrue(resource.contains("TariffRepository"),
                "the value path must read persisted records via the repository");

        String entity = Files.readString(SRC.resolve("ch/tarifhub/serving/TariffRecordEntity.java"));
        assertTrue(entity.contains("@Entity") && entity.contains("\"tariff\""),
                "the value path must be backed by the persisted 'tariff' entity");
    }
}
