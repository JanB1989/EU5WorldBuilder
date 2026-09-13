"""Management on inherited fields is independent of natural-access bookkeeping."""
import numpy as np


def baseline_management(base_fraction,historical_fraction,served,full,baseline_rf,rf,ir,livelihood):
    # Existing cultivated baseline fields are maintained too. The maximum can
    # maintain all baseline fields, without counting those hectares twice.
    management_gain=np.maximum(rf-baseline_rf,0)
    current=np.minimum(base_fraction,historical_fraction)*management_gain
    maximum=base_fraction*management_gain
    # Where the retained baseline has a better dry system, irrigation receives
    # only its benefit above that system, not above a weaker alternative.
    ordinary=np.maximum(ir-np.maximum(rf,livelihood),0)
    baseline=np.maximum(ir-np.maximum.reduce([rf,baseline_rf,livelihood]),0)
    return current,maximum,np.minimum(served,base_fraction)*(baseline-ordinary),np.minimum(full,base_fraction)*(baseline-ordinary)
