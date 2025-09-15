import pytest
from api.utils import ImageUtils

testdata = [
    # original_width, original_height, new_width, new_height
    (2048, 1536, 512, 384),
    (1536, 2048, 384, 512),
    (512, 512, 256, 256),
    (10, 2, 5, 1),
    (2, 10, 1, 5),
]

@pytest.mark.parametrize("original_width, original_height, new_width, new_height", testdata)
def test_image_dimensions_should_be_scaled_correctly_with_width(original_width, original_height, new_width, new_height):
    expected_height = new_height

    width, height = ImageUtils.calculate_scaled_size(
        original_width=original_width, original_height=original_height, width=new_width
    )
    assert width == new_width
    assert height == expected_height


@pytest.mark.parametrize("original_width, original_height, new_width, new_height", testdata)
def test_image_dimensions_should_be_scaled_correctly_with_height(original_width, original_height, new_width, new_height):
    expected_width = new_width

    width, height = ImageUtils.calculate_scaled_size(
        original_width=original_width,
        original_height=original_height,
        height=new_height,
    )
    assert width == expected_width
    assert height == new_height


@pytest.mark.parametrize("original_width, original_height, new_width, new_height", testdata)
def test_image_dimensions_should_be_scaled_correctly_with_all_params(original_width, original_height, new_width, new_height):
    width, height = ImageUtils.calculate_scaled_size(
        original_width=original_width,
        original_height=original_height,
        height=new_height,
    )
    assert width == new_width
    assert height == new_height