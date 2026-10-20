"""On-demand storm tracking sidecar.

Everything in this service lives inside this package, never as a top-level
module. gl-tracker — which this service imports — uses flat top-level module
names (``config``, ``estado``, ``filtro_convectivo``, ``gate``, ``grilla``,
``h0_wrf``, ``pipeline``, ``operativo``). A top-level module of the same name
here would shadow it depending on ``sys.path`` order, which is exactly the kind
of bug that only shows up after a deployment reorders something.
"""
