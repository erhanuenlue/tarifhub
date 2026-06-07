package ch.tarifhub.serving;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.OffsetDateTime;

import io.quarkus.hibernate.orm.panache.PanacheEntityBase;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.xml.bind.annotation.XmlAccessType;
import jakarta.xml.bind.annotation.XmlAccessorType;
import jakarta.xml.bind.annotation.XmlRootElement;

/**
 * Read-only projection of a frozen tariff record (the {@code tariff} table).
 *
 * <p>The serving service NEVER writes or mutates these rows: they are immutable,
 * versioned, hashed facts produced by the ingestion service. No setter logic, no
 * persistence calls — this entity exists only to read frozen values out verbatim.
 * The {@code embedding} and {@code metadata} columns are intentionally not mapped;
 * embeddings are queried natively by the search package.
 */
@Entity
@Table(name = "tariff")
@XmlRootElement(name = "tariff")
@XmlAccessorType(XmlAccessType.FIELD)
public class TariffRecordEntity extends PanacheEntityBase {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    public Long id;

    @Column(name = "tariff_code")
    public String tariffCode;

    @Column(name = "tariff_system")
    public String tariffSystem;

    @Column(name = "designation_de")
    public String designationDe;

    @Column(name = "designation_fr")
    public String designationFr;

    @Column(name = "designation_it")
    public String designationIt;

    public String category;

    @Column(name = "tax_points")
    public BigDecimal taxPoints;

    @Column(name = "price_chf")
    public BigDecimal priceChf;

    public String unit;

    @Column(name = "valid_from")
    public LocalDate validFrom;

    @Column(name = "valid_to")
    public LocalDate validTo;

    @Column(name = "source_url")
    public String sourceUrl;

    @Column(name = "source_version")
    public String sourceVersion;

    @Column(name = "harmonization_confidence")
    public float harmonizationConfidence;

    @Column(name = "requires_review")
    public boolean requiresReview;

    @Column(name = "record_hash")
    public String recordHash;

    public int version;

    @Column(name = "created_at")
    public OffsetDateTime createdAt;
}
