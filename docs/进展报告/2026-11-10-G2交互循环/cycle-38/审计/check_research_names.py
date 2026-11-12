"""Bounded undefined-global check for these ordinary imported research scripts.

This uses Python symbol tables; it is not a general static type checker and does
not validate dynamic attribute access, imports at runtime or arbitrary Python.
"""
import builtins
import symtable


def undefined_globals(source, filename):
    module = symtable.symtable(source, filename, 'exec')
    defined = {s.get_name() for s in module.get_symbols() if s.is_assigned() or s.is_imported()}
    defined.update(vars(builtins))
    defined.update({'__file__', '__name__', '__doc__', '__package__'})
    found = []
    def visit(table):
        for symbol in table.get_symbols():
            if symbol.is_referenced() and symbol.is_global() and symbol.get_name() not in defined:
                found.append({'scope': table.get_name(), 'name': symbol.get_name()})
        for child in table.get_children():
            visit(child)
    visit(module)
    return found
