from imgui_bundle import imgui


def apply_style() -> None:
    imgui.style_colors_dark()
    imgui.get_io().font_default = imgui.get_io().fonts.add_font_default_vector()
    imgui.get_style().font_size_base = 16
    imgui.get_style().frame_padding = imgui.ImVec2(6, 4)
    imgui.get_style().item_spacing = imgui.ImVec2(8, 8)
