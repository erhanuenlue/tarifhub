package ch.tarifhub.serving.search;

import java.util.List;

import io.smallrye.common.annotation.Blocking;
import jakarta.inject.Inject;
import jakarta.ws.rs.DefaultValue;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.QueryParam;
import jakarta.ws.rs.core.MediaType;

/**
 * Semantic search endpoint. Returns frozen records ranked by similarity to the query.
 *
 * <p>Example: {@code GET /api/v1/search?q=blood%20glucose&limit=5}
 */
@Path("/api/v1/search")
@Produces(MediaType.APPLICATION_JSON)
public class SearchResource {

    @Inject
    SemanticSearchService searchService;

    @GET
    @Blocking
    public List<SemanticSearchService.SearchHit> search(
            @QueryParam("q") String query,
            @QueryParam("limit") @DefaultValue("10") int limit) {
        return searchService.search(query, limit);
    }
}
