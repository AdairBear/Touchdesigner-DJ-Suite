g = op('/project1/fire_aura_glsl')
for page in g.pages:
    if page.name.lower() == 'vectors':
        print('Vectors page pars:')
        for p in page.pars:
            print(' ', p.name)
        break
