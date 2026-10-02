"""Legacy removal tests: duplicate generation paths are gone.

  - modules/generator.py (unimported duplicate of post_generator) deleted.
  - SocialMediaPostGenerator.publish_to_facebook/instagram (duplicate Meta
    HTTP; use modules.publisher.UniversalPublisher) deleted.
  - The canonical template path (generate_post / weekly schedule / pipeline)
    still works and emits no deprecation warnings.
"""

import warnings
from pathlib import Path


def test_generator_module_removed():
    assert not Path('modules/generator.py').exists()
    try:
        import modules.generator  # noqa: F401
    except ModuleNotFoundError:
        pass
    else:
        raise AssertionError('modules.generator should not be importable')


def test_post_generator_publish_methods_removed():
    from modules.post_generator import SocialMediaPostGenerator
    assert not hasattr(SocialMediaPostGenerator, 'publish_to_facebook')
    assert not hasattr(SocialMediaPostGenerator, 'publish_to_instagram')


def test_canonical_template_path_works_without_warnings():
    from modules.post_generator import SocialMediaPostGenerator
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        gen = SocialMediaPostGenerator()
        gen.setup_business({'business_name': 'Taco Truck'})
        post = gen.generate_post('instagram_menu', day='Tuesday', date='June 03')
        schedule = gen.generate_weekly_schedule()
    assert post['platform'] == 'instagram'
    assert len(schedule) == 7
    assert [w for w in caught if issubclass(w.category, DeprecationWarning)] == []


def test_pipeline_template_path_works_without_warnings():
    from core.content.pipeline import ContentPipeline
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        out = ContentPipeline().run_template('instagram_location', {'name': 'Taco Truck'})
    assert out['platform'] == 'instagram'
    assert [w for w in caught if issubclass(w.category, DeprecationWarning)] == []
