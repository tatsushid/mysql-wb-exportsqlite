# ExportSQLite: SQLite export plugin for MySQL Workbench
#
# Copyright (C) 2015 Tatsushi Demachi (Python version)
# Copyright (C) 2009 Thomas Henlich (Original Lua version)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import re
import StringIO

import grt
import mforms

from grt.modules import Workbench
from wb import DefineModule, wbinputs
from workbench.ui import WizardForm, WizardPage
from mforms import newButton, newCodeEditor, FileChooser

ModuleInfo = DefineModule(name='ExportSQLite',
                          author='Tatsushi Demachi',
                          version='0.1.0')

@ModuleInfo.plugin('wb.util.exportSQLite',
                   caption='Export SQLite CREATE script',
                   input=[wbinputs.currentCatalog()],
                   groups=['Catalog/Utilities', 'Menu/Catalog'])
@ModuleInfo.export(grt.INT, grt.classes.db_Catalog)
def exportSQLite(cat):
    """Function to go through all schemata in catalog and rename all FKs
    of table-objects
    """

    def validate_for_sqlite_export(cat):
        """Check uniqueness of schema, table and index names. Return 0 on
        success otherwise return 1 (the export process should abort)
        """

        have_errors = False
        idt = {}
        for i, schema in enumerate(cat.schemata):
            if schema.name in idt:
                have_errors = True
                if Workbench.confirm('Name conflict',
                        'Schemas %d and %d have the same name "%s".'
                        ' Please rename one of them.\n'
                        'Search for more such errors?' % (
                            idt[schema.name], i, schema.name)) == 0:
                    return False
            else:
                idt[schema.name] = i

        # Do not continue looking for errors on schema name error
        if have_errors:
            return False

        for schema in cat.schemata:
            idt = {}
            for i, tbl in enumerate(schema.tables):
                if tbl.name == '':
                    have_errors = True
                    if Workbench.confirm('Name conflict',
                            'Table %d in schema "%s". has no name.'
                            ' Please rename.\n'
                            'Search for more such errors?' % (
                                i, schema.name)) == 0:
                        return False
                if tbl.name in idt:
                    have_errors = True
                    if Workbench.confirm('Name conflict',
                            'Tables %d and %d in schema "%s"'
                            ' have the same name "%s".'
                            ' Please rename one of them.\n'
                            'Search for more such errors?' % (
                                idt[tbl.name], i, schema.name, tbl.name)) == 0:
                        return False
                else:
                    idt[tbl.name] = i

        if have_errors:
            return False

        for schema in cat.schemata:
            for tbl in schema.tables:
                idt = {}
                for i, column in enumerate(tbl.columns):
                    if column.name == '':
                        have_errors = True
                        if Workbench.confirm('Name conflict',
                                'Column %d in table "%s"."%s". has no name.'
                                ' Please rename.\n'
                                'Search for more such errors?' % (
                                    i, schema.name, tbl.name)) == 0:
                            return False
                    if column.name in idt:
                        have_errors = True
                        if Workbench.confirm('Name conflict',
                                'Columns %d and %d in table "%s"."%s"'
                                ' have the same name "%s".'
                                ' Please rename one of them.\n'
                                'Search for more such errors?' % (
                                    idt[column.name],
                                    i,
                                    schema.name,
                                    tbl.name,
                                    column.name)) == 0:
                            return False
                    else:
                        idt[column.name] = i

                # Now check indices (except primary/unique)
                idt = {}
                for i, index in enumerate(tbl.indices):
                    if index.indexType == 'INDEX':
                        if index.name == '':
                            have_errors = True
                            if Workbench.confirm('Name conflict',
                                    'Index %d in table "%s"."%s". has no name.'
                                    ' Please rename.\n'
                                    'Search for more such errors?' % (
                                        i, schema.name, tbl.name)) == 0:
                                return False
                        if index.name in idt:
                            have_errors = True
                            if Workbench.confirm('Name conflict',
                                    'Indices %d and %d in table "%s"."%s"'
                                    ' have the same name "%s".'
                                    ' Please rename one of them.\n'
                                    'Search for more such errors?' % (
                                        idt[index.name],
                                        i,
                                        schema.name,
                                        tbl.name,
                                        column.name)) == 0:
                                return False
                        else:
                            idt[index.name] = i

        if have_errors:
            return False

        return True

    def is_deferred(fkey):
        # Hack: if comment starts with "Defer..." we make it a deferred FK could
        # use member 'deferability' (WB has it), but there is no GUI for it
        return fkey.comment.lstrip().lower()[0:5] == 'defer'

    def export_table(out, db_name, schema, tbl):
        if len(tbl.columns) == 0:
            return

        out.write('CREATE TABLE %s%s(\n%s' % (
                  db_name, dq(tbl.name), schema_comment_format(tbl.comment)))

        primary_key = [i for i in tbl.indices if i.isPrimary == 1]
        primary_key = primary_key[0] if len(primary_key) > 0 else None

        pk_column = None
        if primary_key and len(primary_key.columns) == 1:
            pk_column = primary_key.columns[0].referencedColumn

        col_comment = ''
        for i, column in enumerate(tbl.columns):
            check, sqlite_type, flags = '', None, None
            if column.simpleType:
                sqlite_type = column.simpleType.name
                flags = column.simpleType.flags
            else:
                sqlite_type = column.userType.name
                flags = column.flags
            length = column.length
            # For INTEGER PRIMARY KEY column to become an alias for the rowid
            # the type needs to be "INTEGER" not "INT"
            # we fix it for other columns as well
            if 'INT' in sqlite_type or sqlite_type == 'LONG':
                sqlite_type = 'INTEGER'
                length = -1
                # Check flags for "unsigned"
                if 'UNSIGNED' in column.flags:
                    check = dq(column.name) + '>=0'
            # We even implement ENUM (because we can)
            if sqlite_type == 'ENUM':
                sqlite_type = 'TEXT'
                if column.datatypeExplicitParams:
                    check = (dq(column.name) + ' IN' +
                             column.datatypeExplicitParams)
            if i > 0:
                out.write(',' + comment_format(col_comment) + '\n')
            out.write('  ' + dq(column.name))
            # Type is optional in SQLite
            if sqlite_type != '':
                out.write(' ' + sqlite_type)
            # For [VAR]CHAR and such types specify length even though this is
            # not used in SQLite
            if length > 0:
                out.write('(%d)' % length)

            # Must specify single-column PKs as column-constraints for AI/rowid
            # behaviour
            if column == pk_column:
                out.write(' PRIMARY KEY')
                if primary_key.columns[0].descend == 1:
                    out.write(' DESC')
                # Only PK columns can be AI in SQLite
                if column.autoIncrement == 1:
                    out.write(' AUTOINCREMENT')
            # Check for NotNull
            if column.isNotNull == 1:
                out.write(' NOT NULL')

            if check != '':
                out.write(' CHECK(' + check + ')')

            if column.defaultValue != '':
                out.write(' DEFAULT ' + column.defaultValue)

            col_comment = column.comment

        # For multicolumn PKs
        if primary_key and not pk_column:
            out.write(',%s\n  PRIMARY KEY(%s)' % (
                      comment_format(col_comment),
                      print_index_columns(primary_key)))
            col_comment = ''

        # Put non-primary, UNIQUE Keys in CREATE TABLE as well (because we can)
        for index in tbl.indices:
            if index != primary_key and index.indexType == 'UNIQUE':
                out.write(',%s\n' % comment_format(col_comment))
                col_comment = ''
                if index.name != '':
                    out.write('  CONSTRAINT %s\n  ' % dq(index.name))
                out.write('  UNIQUE(%s)' % print_index_columns(index))

        for fkey in tbl.foreignKeys:
            have_fkeys = 1
            out.write(',%s\n' % comment_format(col_comment))
            col_comment = ''
            if fkey.name != '':
                out.write('  CONSTRAINT %s\n  ' % dq(fkey.name))
            out.write('  FOREIGN KEY(%s)\n' % print_fk_columns(fkey.columns))
            out.write('    REFERENCES %s(%s)' % (
                      dq(fkey.referencedTable.name),
                      print_fk_columns(fkey.referencedColumns)))
            if fkey.deleteRule in ['RESTRICT', 'CASCADE', 'SET NULL']:
                out.write('\n    ON DELETE ' + fkey.deleteRule)
            if fkey.updateRule in ['RESTRICT', 'CASCADE', 'SET NULL']:
                out.write('\n    ON UPDATE ' + fkey.updateRule)
            if is_deferred(fkey):
                out.write(' DEFERRABLE INITIALLY DEFERRED')

        out.write(comment_format(col_comment) + '\n);\n')

        # CREATE INDEX statements for all non-primary, non-unique, non-foreign
        # indexes
        for i, index in enumerate(tbl.indices):
            if index.indexType == 'INDEX':
                index_name = tbl.name + '.' + index.name
                if index.name == '':
                    index_name = tbl.name + '.index' + i
                out.write('CREATE INDEX %s%s ON %s (%s);\n' % (
                          db_name,
                          dq(index_name),
                          dq(tbl.name),
                          print_index_columns(index)))

        # Write the INSERTS (currently always)
        for insert in tbl.inserts().splitlines():
            columns_values = ''
            insert_start = 'insert into `%s`.`%s` (' % (schema.name, tbl.name)
            if insert[0:len(insert_start)].lower() == insert_start.lower():
                columns_values = insert[len(insert_start):]
            else:
                raise ExportSQLiteError(
                        'Error', 'Unrecognized command in insert')
            last_column = 0
            for i, column in enumerate(tbl.columns):
                column_name = '`' + column.name + '`'
                if columns_values[0:len(column_name)] == column_name:
                    columns_values = columns_values[len(column_name):]
                    if columns_values[0:1] == ')':
                        columns_values = columns_values[1:]
                        last_column = i
                        break
                    else:
                        if columns_values[0:2] == ', ':
                            columns_values = columns_values[2:]
                        else:
                            raise ExportSQLiteError(
                                    'Error',
                                    'Unrecognized character in column list')
                else:
                    raise ExportSQLiteError(
                            'Error', 'Unrecognized column in inserts')

            out.write('INSERT INTO %s(' % dq(tbl.name))
            for i in range(last_column + 1):
                if i > 0:
                    out.write(',')
                out.write(dq(tbl.columns[i].name))

            if columns_values[0:9].lower() != ' values (':
                raise ExportSQLiteError(
                        'Error', 'Unrecognized SQL in insert')
            columns_values = columns_values[9:]

            out.write(') VALUES(')
            out.write(columns_values.replace("\\'", "''"))
            out.write('\n')

    def order_tables(out, db_name, schema, unordered, respect_deferredness):
        have_ordered = False
        while not have_ordered:
            if len(unordered) == 0:
                have_ordered = True
            for tbl in unordered.values():
                has_forward_reference = False
                for fkey in tbl.foreignKeys:
                    if (fkey.referencedTable.name in unordered and
                            fkey.referencedTable.name != tbl.name and not (
                                respect_deferredness and is_deferred(fkey))):
                        has_forward_reference = True
                        break
                if not has_forward_reference:
                    export_table(out, db_name, schema, tbl)
                    del unordered[tbl.name]
                    have_ordered = True

    def export_schema(out, schema, is_main_schema):
        if len(schema.tables) == 0:
            return

        out.write('\n-- Schema: %s\n' % schema.name)
        out.write(schema_comment_format(schema.comment))

        db_name = ''
        if not is_main_schema:
            db_name = dq(schema.name) + '.'
            out.write('ATTACH "%s" AS %s;\n' % (
                    safe_file_name(schema.name + '.sdb'),
                    dq(schema.name)))
        out.write('BEGIN;\n')

        # Find a valid table order for inserts from FK constraints
        unordered = {t.name: t for t in schema.tables}

        # Try treating deferred keys like non-deferred keys first for ordering
        order_tables(out, db_name, schema, unordered, False)
        # Now try harder (leave out deferred keys from determining an order)
        order_tables(out, db_name, schema, unordered, True)

        # Loop through all remaining tables, if any. Have circular FK refs.
        # How to handle?
        for tbl in unordered.values():
            export_table(out, db_name, schema, tbl)

        out.write('COMMIT;\n')

    def print_index_columns(index):
        s = ''
        for i, column in enumerate(index.columns):
            if i > 0:
                s += ','
            s += dq(column.referencedColumn.name)
            if column.descend == 1:
                s += ' DESC'
        return s

    def print_fk_columns(columns):
        s = ''
        for i, column in enumerate(columns):
            if i > 0:
                s += ','
            s += dq(column.name)
        return s

    def dq(ident):
        """Double quote identifer, replacing " by "" """
        return '"' + re.sub(r'"', '""', ident) + '"'

    def safe_file_name(ident):
        """Create safe filename from identifer"""

        def repl(c):
            return ["%%%02x" % c for c in bytearray(c, 'ascii')]

        return re.sub(r'[/\:*?"<>|%]', repl, ident)

    def info_format(header, body):
        """Format a info field as SQL comment"""
        body = body.strip()
        if body == '':
            return ''
        elif '\n' in body:
            # Multiline comment
            return '-- %s:\n--   %s\n' % (
                        header, re.sub(r'\n', '\n--   ', body))
        else:
            # Single line
            return '-- %-14s %s\n' % (header + ':', body)

    def schema_comment_format(body):
        """Format a schema or table comment as SQL comment
        table comments to be stored in SQLite schema
        """
        body = body.strip()
        if body == '':
            return ''
        else:
            # Multiline comment
            return '--   %s\n' % re.sub(r'\n', '\n--   ', body)

    def comment_format(body):
        body = body.strip()
        if body == '':
            return ''
        elif '\n' in body:
            # Multiline comment
            return '\n--   %s' % re.sub(r'\n', '\n--   ', body)
        else:
            # Single line
            return '-- %s' % body

    if not validate_for_sqlite_export(cat):
        return 1

    out = StringIO.StringIO()
    out.write(info_format(
                'Creator',
                'MySQL Workbench %d.%d.%d/ExportSQLite Plugin %s\n' % (
                    grt.root.wb.info.version.majorNumber,
                    grt.root.wb.info.version.minorNumber,
                    grt.root.wb.info.version.releaseNumber,
                    ModuleInfo.version)))
    out.write(info_format('Author', grt.root.wb.doc.info.author))
    out.write(info_format('Caption', grt.root.wb.doc.info.caption))
    out.write(info_format('Project', grt.root.wb.doc.info.project))
    out.write(info_format('Changed', grt.root.wb.doc.info.dateChanged))
    out.write(info_format('Created', grt.root.wb.doc.info.dateCreated))
    out.write(info_format('Description', grt.root.wb.doc.info.description))

    out.write('PRAGMA foreign_keys = OFF;\n')

    # Loop over all catalogs in schema, find main schema main schema is first
    # nonempty schema or nonempty schema named "main"
    try:
        for schema in [(s, s.name == 'main') for s in cat.schemata]:
            export_schema(out, schema[0], schema[1])
    except ExportSQLiteError as e:
        Workbench.confirm(e.typ, e.message)
        return 1

    sql_text = out.getvalue()
    out.close()

    wizard = ExportSQLiteWizard(sql_text)
    wizard.run()

    return 0

class ExportSQLiteError(Exception):
    def __init__(self, typ, message):
        self.typ = typ
        self.message = message

    def __str__(self):
        return repr(self.typ) + ': ' + repr(self.message)

class ExportSQLiteWizard_PreviewPage(WizardPage):
    def __init__(self, owner, sql_text):
        WizardPage.__init__(self, owner, 'Review Generated Script')

        self.save_button = mforms.newButton()
        self.save_button.enable_internal_padding(True)
        self.save_button.set_text('Save to File...')
        self.save_button.set_tooltip('Save the text to a new file.')
        self.save_button.add_clicked_callback(self.save_clicked)

        self.copy_button = mforms.newButton()
        self.copy_button.enable_internal_padding(True)
        self.copy_button.set_text('Copy to Clipboard')
        self.copy_button.set_tooltip('Copy the text to the clipboard.')
        self.copy_button.add_clicked_callback(self.copy_clicked)

        self.sql_text = mforms.newCodeEditor()
        self.sql_text.set_language(mforms.LanguageMySQL)
        self.sql_text.set_text(sql_text)

    def go_cancel(self):
        self.main.finish()

    def create_ui(self):
        button_box = mforms.newBox(True)
        button_box.set_padding(8)

        button_box.add(self.save_button, False, True)
        button_box.add(self.copy_button, False, True)

        self.content.add_end(button_box, False, False)
        self.content.add_end(self.sql_text, True, True)

    def save_clicked(self):
        file_chooser = mforms.newFileChooser(self.main, mforms.SaveFile)
        file_chooser.set_extensions('SQL Files (*.sql)|*.sql', 'sql')
        if file_chooser.run_modal() == mforms.ResultOk:
            path = file_chooser.get_path()
            text = self.sql_text.get_text(False)
            try:
                with open(path, 'w+') as f:
                    f.write(text)
            except IOError as e:
                mforms.Utilities.show_error(
                    'Save to File',
                    'Could not save to file "%s": %s' % (path, str(e)),
                    'OK')

    def copy_clicked(self):
        mforms.Utilities.set_clipboard_text(self.sql_text.get_text(False))

class ExportSQLiteWizard(WizardForm):
    def __init__(self, sql_text):
        WizardForm.__init__(self, None)

        self.set_name('sqlite_export_wizard')
        self.set_title('SQLite Export Wizard')

        self.preview_page = ExportSQLiteWizard_PreviewPage(self, sql_text)
        self.add_page(self.preview_page)
