# Plant Database

A work-in-progress plant database for planting design and stormwater work. I'm figuring out how to structure the data so it can drive plant searches, bloom charts, and simple environmental benefit charts.

It's still early. Most of the plant info is placeholder.

## Files

- `schema.sql`: the database (SQLite)
- `index.html`: a preview page to click around in

To see the preview, open `index.html` in a browser. To look at the database itself, import `schema.sql` into [DB Browser for SQLite](https://sqlitebrowser.org/).

## How it's set up

- One row per plant. Things a plant can have several of (sun conditions, soil moisture, uses, wildlife value, native region) get their own tables so they can be filtered cleanly.
- Sun, soil moisture, and plant type are fixed lists, so entries stay consistent.
- Bloom time is stored as a start month, an end month, and a color, so a bloom chart can be drawn from it.
- Photos are stored by type (whole plant, leaf, flower, fruit) with credit and license.
- Environmental numbers, like CO2 and rainfall interception, live in their own table. Each one needs a source, a unit, and what it's per. If there's no source, there's no number.

## About the data

- The 12 plants in the preview are placeholders. Check them before using them.
- Red maple is the only plant with sourced numbers. They come from the USDA Forest Service *Piedmont Community Tree Guide* (McPherson et al., 2005). They're modeled estimates for a typical large street or park tree, based on Charlotte, NC, and the guide calls them first-order approximations.
- Net CO2 reduced per year is not the same as carbon stored, and rainfall intercepted is not the same as avoided runoff, so they're kept as separate measures.
- Saved lists in the preview only live in your own browser.

## Next

- Add the 5-year values from the Piedmont guide so the bar charts become a line over time
- Add stormwater tolerance fields (wetland status, flooding, drought, and salt tolerance) with sources
- Add quantities and planting zones for projects
- Plant palette export with photos
