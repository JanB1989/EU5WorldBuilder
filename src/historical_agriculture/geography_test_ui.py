"""Native modifier-effect rows scoped to the selected attribute value."""
def attribute_effect_rows(grade_key, modifier_keys):
    return '\n'.join(f'''                                                TooltipStringPairList = {{
                                                    visible = "[EqualTo_CFixedPoint(LocationView.GetLocation.GetModifierValueFixed('{grade_key}'), '(CFixedPoint){grade}')]"
                                                    textcontext = "[ShowModifierEffect('{modifier}')]"
                                                }}''' for grade,modifier in enumerate(modifier_keys,1))