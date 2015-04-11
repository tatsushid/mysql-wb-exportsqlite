# MySQL Workbench ExportSQLite Plugin

ExportSQLite is a plugin for
[MySQL Workbench](http://www.mysql.com/products/workbench/) to export a schema
catalog as SQLite's CREATE SQL queries. This is a Python port of
[original Lua script](https://gist.github.com/mrprompt/7252060) for using with
MySQL Workbench 6.2 or above.

## Installation

1. Open MySQL Workbench
2. Choose "Install Plugin/Module..." in "Scripting" menu
3. Open `export_sqlite_grt.py` file
4. Restart MySQL Workbench

## Usage

Once you open a database model in MySQL Workbench, you can see "Export SQLite
CREATE script" in "Tools > Catalog" menu. Just choose it.

## License

The original Lua plugin is released under GPLv3 so this Python version
inherits it.
