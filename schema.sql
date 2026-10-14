-- =====================================================================
-- Plant Database - Phase 1 schema (SQLite)
-- Design goals:
--   1. One plant = one row. Anything one-to-many gets its own table.
--   2. Controlled vocabularies (lookup tables) instead of free text.
--   3. Numeric / structured fields so a bloom chart or plant palette
--      graphic can be generated later without cleaning data first.
--   4. Surrogate keys everywhere, so future modules (vendors, projects)
--      can reference plants by ID, not by name.
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- LOOKUP TABLES (controlled vocabularies)
-- ---------------------------------------------------------------------

CREATE TABLE plant_type (            -- Perennial, Grass, Shrub, Tree, Groundcover...
    plant_type_id   INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE
);

CREATE TABLE sun_exposure (          -- Full Sun, Part Shade, Shade
    sun_exposure_id INTEGER PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE
);

CREATE TABLE soil_moisture (         -- Dry, Medium, Moist, Wet
    soil_moisture_id INTEGER PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE,
    sort_order       INTEGER NOT NULL      -- dry -> wet, for range queries
);

CREATE TABLE landscape_use (         -- Bioretention, Screening, Pollinator, Erosion control...
    landscape_use_id INTEGER PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE
);

CREATE TABLE wildlife_value (        -- Bees, Butterflies, Birds, Hummingbirds
    wildlife_value_id INTEGER PRIMARY KEY,
    name              TEXT NOT NULL UNIQUE
);

CREATE TABLE region (                -- Used for native range, e.g. 'Eastern U.S.', 'Mid-Atlantic'
    region_id INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE
);

-- ---------------------------------------------------------------------
-- CORE TABLE
-- ---------------------------------------------------------------------

CREATE TABLE plant (
    plant_id            INTEGER PRIMARY KEY,
    botanical_name      TEXT NOT NULL UNIQUE,   -- includes cultivar, e.g. Liatris spicata 'Kobold'
    common_name         TEXT NOT NULL,
    plant_type_id       INTEGER REFERENCES plant_type(plant_type_id),

    -- Size stored numerically, in inches, so layouts can format "2-3 ft" etc.
    height_min_in       REAL CHECK (height_min_in >= 0),
    height_max_in       REAL CHECK (height_max_in >= height_min_in),
    spread_min_in       REAL CHECK (spread_min_in >= 0),
    spread_max_in       REAL CHECK (spread_max_in >= spread_min_in),

    -- USDA hardiness zone range (e.g. 4 to 8)
    zone_min            INTEGER CHECK (zone_min BETWEEN 1 AND 13),
    zone_max            INTEGER CHECK (zone_max BETWEEN zone_min AND 13),

    -- Moisture and sun are ranges / sets, handled below; these are simple flags
    deer_resistant      INTEGER CHECK (deer_resistant IN (0, 1)),
    pollutant_tolerant  INTEGER CHECK (pollutant_tolerant IN (0, 1)),
    bioswale_suitable   INTEGER CHECK (bioswale_suitable IN (0, 1)),

    -- Bloom: month numbers 1-12. NULL for non-flowering plants.
    -- bloom_end < bloom_start means it wraps the new year (rare; flag it in QA).
    bloom_start_month   INTEGER CHECK (bloom_start_month BETWEEN 1 AND 12),
    bloom_end_month     INTEGER CHECK (bloom_end_month BETWEEN 1 AND 12),
    bloom_color_hex     TEXT,                    -- e.g. '#E8D44D', drives bloom chart color

    comments            TEXT
);

-- ---------------------------------------------------------------------
-- JUNCTION TABLES (many-to-many attributes)
-- ---------------------------------------------------------------------

CREATE TABLE plant_sun_exposure (
    plant_id        INTEGER NOT NULL REFERENCES plant(plant_id) ON DELETE CASCADE,
    sun_exposure_id INTEGER NOT NULL REFERENCES sun_exposure(sun_exposure_id),
    PRIMARY KEY (plant_id, sun_exposure_id)
);

CREATE TABLE plant_soil_moisture (
    plant_id         INTEGER NOT NULL REFERENCES plant(plant_id) ON DELETE CASCADE,
    soil_moisture_id INTEGER NOT NULL REFERENCES soil_moisture(soil_moisture_id),
    PRIMARY KEY (plant_id, soil_moisture_id)
);

CREATE TABLE plant_landscape_use (
    plant_id         INTEGER NOT NULL REFERENCES plant(plant_id) ON DELETE CASCADE,
    landscape_use_id INTEGER NOT NULL REFERENCES landscape_use(landscape_use_id),
    PRIMARY KEY (plant_id, landscape_use_id)
);

CREATE TABLE plant_wildlife_value (
    plant_id          INTEGER NOT NULL REFERENCES plant(plant_id) ON DELETE CASCADE,
    wildlife_value_id INTEGER NOT NULL REFERENCES wildlife_value(wildlife_value_id),
    PRIMARY KEY (plant_id, wildlife_value_id)
);

CREATE TABLE plant_native_region (
    plant_id  INTEGER NOT NULL REFERENCES plant(plant_id) ON DELETE CASCADE,
    region_id INTEGER NOT NULL REFERENCES region(region_id),
    PRIMARY KEY (plant_id, region_id)
);

-- ---------------------------------------------------------------------
-- IMAGES (supports a future plant palette graphic; tracks credit/license)
-- ---------------------------------------------------------------------

CREATE TABLE image_type (            -- what the photo shows; palette layouts pull by type
    image_type_id INTEGER PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    sort_order    INTEGER NOT NULL       -- order the slots appear in a palette
);

CREATE TABLE plant_image (
    image_id      INTEGER PRIMARY KEY,
    plant_id      INTEGER NOT NULL REFERENCES plant(plant_id) ON DELETE CASCADE,
    image_type_id INTEGER NOT NULL REFERENCES image_type(image_type_id),
    file_path     TEXT NOT NULL,          -- e.g. images/rudbeckia-fulgida-flower-1.jpg
    credit        TEXT,                   -- photographer / source
    license       TEXT,                   -- e.g. 'Own work', 'CC BY 4.0'
    is_primary    INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0, 1))
);
-- Several photos of one type are allowed (e.g. 3 flower shots).
-- is_primary marks the one a palette should use by default.
CREATE UNIQUE INDEX one_primary_per_type
    ON plant_image(plant_id, image_type_id) WHERE is_primary = 1;

-- ---------------------------------------------------------------------
-- BENEFIT ESTIMATES (optional, many per plant, always with a source)
-- Carbon, rainfall interception, avoided runoff... Not columns on plant:
-- published values differ by age, size, region and method, and most plants
-- have none. A plant with no rows simply has no trustworthy estimate yet.
-- Several rows at different tree_age_yr values make a time series (a chart).
-- ---------------------------------------------------------------------

CREATE TABLE plant_benefit_estimate (
    estimate_id  INTEGER PRIMARY KEY,
    plant_id     INTEGER NOT NULL REFERENCES plant(plant_id) ON DELETE CASCADE,
    metric       TEXT NOT NULL CHECK (metric IN (
                     'stored_carbon',
                     'annual_sequestration',
                     'annual_net_co2_reduction',
                     'annual_rainfall_intercepted',
                     'annual_avoided_runoff')),
    value        REAL NOT NULL CHECK (value >= 0),
    unit         TEXT NOT NULL,           -- C and CO2 are NOT interchangeable
    basis        TEXT NOT NULL,           -- what the value is per, e.g. 'per tree'
    tree_age_yr  INTEGER,                 -- age (or size) the value applies to
    region_id    INTEGER REFERENCES region(region_id),
    source       TEXT NOT NULL,           -- citation or dataset name
    source_year  INTEGER,
    method       TEXT,                    -- e.g. 'allometric equation', 'i-Tree Eco', 'field study'
    notes        TEXT,                    -- e.g. weather data used, conversion factor used
    CHECK (
        (metric = 'stored_carbon'         AND unit IN ('kg C', 'kg CO2e')) OR
        (metric = 'annual_sequestration'  AND unit IN ('kg C/yr', 'kg CO2e/yr')) OR
        (metric = 'annual_net_co2_reduction' AND unit IN ('lb CO2/yr', 'kg CO2/yr')) OR
        (metric IN ('annual_rainfall_intercepted', 'annual_avoided_runoff')
                                          AND unit IN ('m3/yr', 'gal/yr'))
    )
);

-- ---------------------------------------------------------------------
-- FUTURE MODULES (stubs, so Phase 1 isn't a dead end)
-- ---------------------------------------------------------------------

CREATE TABLE vendor (
    vendor_id INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE
);

CREATE TABLE plant_vendor (          -- "we can buy this plant from this vendor"
    plant_id  INTEGER NOT NULL REFERENCES plant(plant_id) ON DELETE CASCADE,
    vendor_id INTEGER NOT NULL REFERENCES vendor(vendor_id) ON DELETE CASCADE,
    PRIMARY KEY (plant_id, vendor_id)
);

CREATE TABLE project (
    project_id INTEGER PRIMARY KEY,
    name       TEXT NOT NULL
);

CREATE TABLE project_plant (         -- a project's saved plant list
    project_id INTEGER NOT NULL REFERENCES project(project_id) ON DELETE CASCADE,
    plant_id   INTEGER NOT NULL REFERENCES plant(plant_id),
    note       TEXT,                     -- e.g. 'use at basin edge'
    added_on   TEXT NOT NULL DEFAULT (date('now')),
    PRIMARY KEY (project_id, plant_id)
);

CREATE TABLE firm_saved_plant (      -- the firm-wide master list (approved / go-to plants)
    plant_id INTEGER PRIMARY KEY REFERENCES plant(plant_id) ON DELETE CASCADE,
    note     TEXT,
    added_on TEXT NOT NULL DEFAULT (date('now'))
);
-- Later: add a staff table and an added_by column to both, to track who saved what.

-- ---------------------------------------------------------------------
-- SEED: vocabularies + two PLACEHOLDER plants (replace with your own data)
-- ---------------------------------------------------------------------

INSERT INTO plant_type (name) VALUES ('Perennial'), ('Grass'), ('Shrub'), ('Tree'), ('Groundcover'), ('Vine');
INSERT INTO sun_exposure (name) VALUES ('Full Sun'), ('Part Shade'), ('Shade');
INSERT INTO soil_moisture (name, sort_order) VALUES ('Dry', 1), ('Medium', 2), ('Moist', 3), ('Wet', 4);
INSERT INTO landscape_use (name) VALUES ('Bioretention'), ('Pollinator Habitat'), ('Erosion Control'), ('Screening'), ('Rain Garden'), ('Shade Tree');
INSERT INTO wildlife_value (name) VALUES ('Bees'), ('Butterflies'), ('Birds'), ('Hummingbirds');
INSERT INTO region (name) VALUES ('Eastern U.S.'), ('Mid-Atlantic'), ('Piedmont');
INSERT INTO image_type (name, sort_order) VALUES ('Whole Plant', 1), ('Leaf / Foliage', 2), ('Flower', 3), ('Fruit / Seed', 4), ('Bark / Stem', 5), ('Fall Color', 6);

-- Placeholder rows: verify every value before treating as real data.
INSERT INTO plant (botanical_name, common_name, plant_type_id,
                   height_min_in, height_max_in, spread_min_in, spread_max_in,
                   zone_min, zone_max, deer_resistant, bioswale_suitable,
                   bloom_start_month, bloom_end_month, bloom_color_hex, comments)
VALUES
 ('Rudbeckia fulgida', 'Orange Coneflower', 1,
  24, 36, 18, 24, 3, 9, 1, 1, 7, 10, '#F2C200', 'PLACEHOLDER - verify'),
 ('Schizachyrium scoparium', 'Little Bluestem', 2,
  24, 48, 12, 24, 3, 9, 1, 1, NULL, NULL, NULL, 'PLACEHOLDER - verify'),
 ('Acer rubrum', 'Red Maple', 4,
  480, 720, 360, 600, 3, 9, 0, 1, 3, 4, '#B5372B', 'PLACEHOLDER - verify'),
 ('Ginkgo biloba', 'Ginkgo', 4,
  600, 960, 360, 480, 3, 8, 1, 0, NULL, NULL, NULL, 'PLACEHOLDER - verify');

-- ---------------------------------------------------------------------
-- SOURCED BENEFIT ESTIMATES (red maple only; everything else has none yet)
-- Source: McPherson, E.G.; Simpson, J.R.; Peper, P.J.; Gardner, S.L.; Vargas, K.E.;
--   Maco, S.E.; Xiao, Q. 2005. Piedmont Community Tree Guide: Benefits, Costs, and
--   Strategic Planting. USDA Forest Service, Pacific Southwest Research Station.
-- Values are for the guide's representative LARGE tree (red maple) at a PUBLIC
-- (street/park) site, per tree planted, with mortality included. Modeled from
-- Charlotte, NC street-tree growth curves; the guide calls them first-order
-- approximations. Rainfall interception is NOT the same as avoided runoff.
-- ---------------------------------------------------------------------

INSERT INTO plant_benefit_estimate
    (plant_id, metric, value, unit, basis, tree_age_yr, region_id, source, source_year, method, notes)
SELECT p.plant_id, v.metric, v.value, v.unit, v.basis, v.age, r.region_id,
       v.source, 2005, 'Forest Service STRATUM modeling, representative tree',
       'Per tree planted, mortality included. First-order approximation; Charlotte NC basis.'
FROM plant p, region r,
 (SELECT 'annual_net_co2_reduction' AS metric, 247.0  AS value, 'lb CO2/yr' AS unit,
         'per tree, public site, year 20' AS basis, 20 AS age,
         'Piedmont Community Tree Guide (2005), Table 2, p. 34' AS source
  UNION ALL SELECT 'annual_net_co2_reduction', 340.0, 'lb CO2/yr',
         'per tree, public site, 40-year average', NULL,
         'Piedmont Community Tree Guide (2005), Table 4, p. 41'
  UNION ALL SELECT 'annual_rainfall_intercepted', 3067.0, 'gal/yr',
         'per tree, public site, year 20', 20,
         'Piedmont Community Tree Guide (2005), Table 2, p. 34'
  UNION ALL SELECT 'annual_rainfall_intercepted', 4778.0, 'gal/yr',
         'per tree, public site, 40-year average', NULL,
         'Piedmont Community Tree Guide (2005), p. 36 and Table 4, p. 41') v
WHERE p.botanical_name = 'Acer rubrum' AND r.name = 'Piedmont';
