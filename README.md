# Plant Database

A work-in-progress plant database for planting design and stormwater work. I'm figuring out how to structure the data so it can drive plant searches, bloom charts, and simple environmental benefit charts.

It's still early. The plant list comes from the firm's plant spreadsheet, and many plants are still missing details.

## Files

- `schema.sql`: the database (SQLite)
- `index.html`: a preview page to click around in
- `scripts/import_spreadsheet.py`: loads the plant spreadsheet into both files above

To see the preview, open `index.html` in a browser. To look at the database itself, import `schema.sql` into [DB Browser for SQLite](https://sqlitebrowser.org/).

## How it's set up

- One row per plant. Things a plant can have several of (sun conditions, soil moisture, uses, wildlife value, native region) get their own tables so they can be filtered cleanly.
- Sun, soil moisture, soil condition, foliage, season, and plant type are fixed lists, so entries stay consistent.
- Yes/no flags (deer resistant, bioswale suitable, toxic...) can also be blank, meaning unknown. Blank is not the same as no.
- Native range can be recorded at several levels (nation, multi-state, state, ecoregion, local), each marked native or introduced, with a source.
- Bloom time is stored as a start month, an end month, and a color, so a bloom chart can be drawn from it.
- Photos are stored by type (whole plant, leaf, flower, fruit) with credit and license.
- Environmental numbers, like CO2 and rainfall interception, live in their own table. Each one needs a source, a unit, and what it's per. If there's no source, there's no number.

## Updating the plant list

The plant rows in `schema.sql` and the list in `index.html` are generated from the spreadsheet. To change a plant, fix it in the spreadsheet and re-run:

```
pip install openpyxl
python3 scripts/import_spreadsheet.py path/to/Plant_Data_Base.xlsx
```

The script prints anything it had to guess at. How the sheet's columns are read:

- Unchecked boxes are stored as unknown, not "no". Blank cells and `(1) Category` are treated as empty.
- Heights and widths become inches. A size with no unit is read as feet.
- Light Requirements becomes sun conditions (e.g. "Full Sun/ Partial Shade" becomes Full Sun and Part Shade).
- Both soil columns become soil moisture (Dry, Medium, Moist, Wet) and soil conditions (sandy, acidic, well drained...). The original wording is kept in `soil_notes`.
- Time of Flowering becomes bloom months: Early Spring = Mar-Apr, Spring = Apr-May, Late Spring = May-Jun, Summer = Jun-Aug, Late Summer = Aug-Sep, Fall = Sep-Oct, Winter = Dec-Feb. The original wording is kept in `bloom_time_notes`.
- Flower Color becomes a bloom chart color, taken from the first color named.
- Bio-swale also tags the plant for Bioretention.
- Native (Yes / -1 / No / 0) is kept as entered in `native_as_entered`, since the sheet doesn't say native to where.
- Plants listed twice are merged into one row.
- The Attachments column (photo counts) isn't imported, since the photos aren't in the sheet.

## About the data

- Plant details come from the spreadsheet as entered. Check them before using them.
- Botanical names are formatted the USDA PLANTS way (genus capitalized, the rest lowercase, ×hybrid, cultivars in quotes), and obvious misspellings were fixed. They haven't been checked against USDA's accepted names yet, so some may be outdated synonyms.
- Red maple is the only plant with sourced numbers. They come from the USDA Forest Service *Piedmont Community Tree Guide* (McPherson et al., 2005). They're modeled estimates for a typical large street or park tree, based on Charlotte, NC, and the guide calls them first-order approximations.
- Net CO2 reduced per year is not the same as carbon stored, and rainfall intercepted is not the same as avoided runoff, so they're kept as separate measures.
- Saved lists in the preview only live in your own browser.

## Next

- Check botanical names against USDA PLANTS, fill in `usda_symbol`, and pull in USDA native status for the nation and state levels
- Fill in the plants that only have a name and type

- Add the 5-year values from the Piedmont guide so the bar charts become a line over time
- Add stormwater tolerance fields (wetland status, flooding, drought, and salt tolerance) with sources
- Add quantities and planting zones for projects
- Plant palette export with photos
