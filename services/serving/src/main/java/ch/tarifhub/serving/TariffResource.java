package ch.tarifhub.serving;

import java.util.List;

import io.smallrye.common.annotation.Blocking;
import jakarta.inject.Inject;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.NotFoundException;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.PathParam;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;

/**
 * Deterministic read API over frozen tariff records.
 *
 * <p>This is the authoritative value path: every value returned is an unaltered,
 * frozen, versioned record read straight from the system of record. No AI is on this
 * path. Content negotiation serves JSON or XML from the same entity.
 */
@Path("/api/v1/tariffs")
@Produces({MediaType.APPLICATION_JSON, MediaType.APPLICATION_XML})
public class TariffResource {

    @Inject
    TariffRepository repository;

    @GET
    @Blocking
    public List<TariffRecordEntity> list() {
        return repository.listAllRecords();
    }

    @GET
    @Path("/{system}/{code}")
    @Blocking
    public TariffRecordEntity byKey(@PathParam("system") String system, @PathParam("code") String code) {
        return repository.findBySystemAndCode(system, code)
                .orElseThrow(() -> new NotFoundException(
                        "no frozen record for system=" + system + " code=" + code));
    }
}
