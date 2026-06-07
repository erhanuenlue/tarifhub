package ch.tarifhub.serving;

import java.util.List;
import java.util.Optional;

import io.quarkus.hibernate.orm.panache.PanacheRepositoryBase;
import io.quarkus.panache.common.Sort;
import jakarta.enterprise.context.ApplicationScoped;

/**
 * Read repository over frozen tariff records.
 *
 * <p>Only read operations are exposed. The semantic-search helper returns the same
 * frozen entities ranked by vector similarity — it ranks, it never fabricates values.
 */
@ApplicationScoped
public class TariffRepository implements PanacheRepositoryBase<TariffRecordEntity, Long> {

    /** All frozen records, ordered deterministically. */
    public List<TariffRecordEntity> listAllRecords() {
        return listAll(Sort.by("tariffSystem").and("tariffCode").and("version"));
    }

    /** Highest version of a record for a (system, code) key. */
    public Optional<TariffRecordEntity> findBySystemAndCode(String system, String code) {
        return find("tariffSystem = ?1 and tariffCode = ?2", Sort.by("version").descending(), system, code)
                .firstResultOptional();
    }

    /**
     * Nearest neighbours by cosine distance on the pgvector {@code embedding} column.
     * Returns the frozen rows themselves (mapped to the entity), ranked by similarity.
     * The query vector is supplied by the search package from its embedding model.
     */
    @SuppressWarnings("unchecked")
    public List<TariffRecordEntity> searchByEmbedding(float[] embedding, int limit) {
        String vectorLiteral = toVectorLiteral(embedding);
        return getEntityManager()
                .createNativeQuery(
                        "SELECT t.* FROM tariff t "
                                + "WHERE t.embedding IS NOT NULL "
                                + "ORDER BY t.embedding <=> CAST(:vec AS vector) "
                                + "LIMIT :lim",
                        TariffRecordEntity.class)
                .setParameter("vec", vectorLiteral)
                .setParameter("lim", limit)
                .getResultList();
    }

    private static String toVectorLiteral(float[] embedding) {
        StringBuilder sb = new StringBuilder("[");
        for (int i = 0; i < embedding.length; i++) {
            if (i > 0) {
                sb.append(',');
            }
            sb.append(embedding[i]);
        }
        return sb.append(']').toString();
    }
}
