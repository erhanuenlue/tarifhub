package ch.tarifhub.serving.search;

import java.util.ArrayList;
import java.util.List;

import ch.tarifhub.serving.TariffRecordEntity;
import ch.tarifhub.serving.TariffRepository;
import dev.langchain4j.data.embedding.Embedding;
import dev.langchain4j.model.embedding.EmbeddingModel;
import jakarta.enterprise.context.ApplicationScoped;
import jakarta.enterprise.inject.Instance;
import jakarta.inject.Inject;
import jakarta.ws.rs.ServiceUnavailableException;

/**
 * AI semantic search over frozen tariff records.
 *
 * <p>This is the ONLY package in the serving service permitted to reference
 * langchain4j. It embeds the free-text query with a langchain4j {@link EmbeddingModel}
 * (in production the same multilingual-e5 model whose vectors ingestion wrote to the
 * pgvector column), then asks the repository for the nearest frozen rows.
 *
 * <p>It RANKS and may explain; it never fabricates or mutates a value. Every field in
 * every hit is an unaltered frozen record straight from the system of record. An
 * optional Anthropic chat model (langchain4j) can summarise <em>why</em> results match
 * — operating only over the returned frozen text — but that is a non-value seam.
 */
@ApplicationScoped
public class SemanticSearchService {

    @Inject
    Instance<EmbeddingModel> embeddingModel;

    @Inject
    TariffRepository repository;

    public List<SearchHit> search(String query, int limit) {
        if (query == null || query.isBlank()) {
            return List.of();
        }
        if (embeddingModel.isUnsatisfied()) {
            throw new ServiceUnavailableException(
                    "semantic search is not configured: wire a langchain4j EmbeddingModel "
                            + "(multilingual-e5, dimension matching the pgvector column)");
        }

        Embedding queryVector = embeddingModel.get().embed(query).content();
        List<TariffRecordEntity> nearest = repository.searchByEmbedding(queryVector.vector(), limit);

        List<SearchHit> hits = new ArrayList<>(nearest.size());
        int rank = 1;
        for (TariffRecordEntity record : nearest) {
            hits.add(new SearchHit(rank++, record));
        }
        return hits;
    }

    /** A ranked search hit wrapping a frozen record (values returned verbatim). */
    public record SearchHit(int rank, TariffRecordEntity record) {
    }
}
