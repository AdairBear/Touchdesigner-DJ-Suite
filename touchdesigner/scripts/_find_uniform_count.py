g = op('/project1/fire_aura_glsl')
# Find any parameter that might control uniform count
for p in g.pars():
    n = p.name.lower()
    if 'uniform' in n or 'vectors' in n or 'count' in n and 'vec' in n:
        print(p.name, '=', p.val)
# Also dump parameter pages
print('\nPages:')
for page in g.pages:
    print('  -', page.name, '(', len(page.pars), 'pars )')
