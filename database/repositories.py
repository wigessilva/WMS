from .repos.produtos import UnitsRepo, FamiliesRepo, ProductsRepo, ProductAliasRepo, UnitAliasRepo
from .repos.estoque import LocationsRepo, AddressesRepo, LpnRepo
from .repos.recebimento import OcRepo, RecebimentoRepo
from .repos.sistema import PrintersRepo, PrinterConfig, GlobalPolicies
from .repos.estoque import AreasRepo
from utils.helpers import bus

# --- INSTANCIAÇÃO DOS REPOSITÓRIOS ---

# Nível 1: Básicos
units_repo = UnitsRepo()
families_repo = FamiliesRepo(event_bus=bus)
locations_repo = LocationsRepo()
printers_repo = PrintersRepo()
oc_repo = OcRepo()
areas_repo = AreasRepo()
unit_alias_repo = UnitAliasRepo(event_bus=bus)

# Nível 2: Com dependências
products_repo = ProductsRepo(event_bus=bus)
addresses_repo = AddressesRepo(event_bus=bus)

printer_config = PrinterConfig(printers_repo=printers_repo)
global_policies = GlobalPolicies(event_bus=bus)

# Nível 3: Complexos
product_alias_repo = ProductAliasRepo(event_bus=bus)
lpn_repo = LpnRepo(event_bus=bus)

# Nível 4: O "Chefe" (Recebimento)
recebimento_repo = RecebimentoRepo(
    oc_repo=oc_repo,
    products_repo=products_repo,
    lpn_repo=lpn_repo,
    locations_repo=locations_repo,
    addresses_repo=addresses_repo,
    product_alias_repo=product_alias_repo,
    units_repo=units_repo,
    unit_alias_repo=unit_alias_repo,
    global_policies=global_policies,
    event_bus=bus
)