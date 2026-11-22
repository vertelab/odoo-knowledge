from . import test_joplin_api
# #if VERSION <= "19.0"
# joplin_sync.py is not in the 20.0 tree, so this suite has nothing to import
# there. Conditioned rather than deleted: the module is still on 18/19.
from . import test_joplin_sync_visibility
# #endif
