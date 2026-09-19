import re
import pytest
from historical_agriculture.geography_test_native_view import guard_location_models


def arguments(text):
    parts=[]; start=0; depth=0; quote=None
    for i,c in enumerate(text):
        if quote:
            if c==quote: quote=None
        elif c in "\"'":quote=c
        elif c=='(':depth+=1
        elif c==')':depth-=1
        elif c==',' and depth==0:parts.append(text[start:i].strip());start=i+1
    return parts+[text[start:].strip()]


def evaluate(expr, values):
    expr=expr.strip()
    if expr in values:return values[expr]
    if expr.startswith("'(int32)"):return int(expr[8:-1])
    fn,body=expr.split('(',1)
    args=[evaluate(a,values) for a in arguments(body[:-1])]
    if fn=='GetDataModelSize':return len(args[0])
    if fn=='Min_int32':return min(args)
    if fn=='Max_int32':return max(args)
    if fn=='Subtract_int32':return args[0]-args[1]
    if fn=='DataModelSkipFirst':
        data,skip=args
        assert 0<=skip<=len(data), 'negative reshape requested'
        return data[skip:]
    if fn=='DataModelRepeatedItem':
        assert args[0]>=0, 'negative repeat count'
        return [None]*args[0]
    raise AssertionError(expr)


def transformed(expression):
    gui='datamodel = "['+expression+']"'
    return re.search(r'"\[(.*)\]"',guard_location_models(gui))[1]


@pytest.mark.parametrize('size',[0,1,4,5,8,9,12])
@pytest.mark.parametrize('skip',[1,5,8,9])
def test_empty_and_short_lists_never_request_negative_reshape(size,skip):
    model='LocationView.GetLocationBuildings(PopType.Self)'
    expr=f"DataModelSkipFirst({model}, '(int32){skip}')"
    data=list(range(size))
    assert evaluate(transformed(expr),{model:data})==data[skip:]


@pytest.mark.parametrize('available,visible',[(0,1),(0,0),(1,2),(2,2),(5,2),(10,5)])
def test_hidden_slot_repeater_never_requests_negative_count(available,visible):
    expr='DataModelRepeatedItem(Subtract_int32(AvailableSlots, VisibleSlots))'
    result=evaluate(transformed(expr),{'AvailableSlots':available,'VisibleSlots':visible})
    assert len(result)==max(0,available-visible)


def test_direct_slot_repeater_also_clamps_negative_values():
    assert evaluate(transformed('DataModelRepeatedItem(Slots)'),{'Slots':-1})==[]


def test_gui_guard_leaves_other_content_and_comments_unchanged():
    original='# datamodel = "[DataModelSkipFirst(Model, \'(int32)1\')]"\nvisible = no\ntexture = "unchanged"\ndatamodel = "[DataModelFirst(Model, \'(int32)2\')]"'
    assert guard_location_models(original)==original


def test_guard_handles_nested_calls_and_is_idempotent():
    gui='blockoverride "model" { datamodel = "[DataModelSkipFirst(GetModel(A, B), \'(int32)9\')]" }'
    result=guard_location_models(gui)
    assert 'GetDataModelSize(GetModel(A, B))' in result
    assert guard_location_models(result)==result
    assert result.endswith(']" }')
