# Publishing to PyPI

Releases go out through GitHub Actions trusted publishing (OIDC). There is no API token to store or rotate.

## One-time setup (done by the PyPI account owner)

1. Sign in at https://pypi.org and open **Account settings → Publishing**
   (https://pypi.org/manage/account/publishing/).
2. Under **Add a new pending publisher → GitHub**, fill in exactly:

   | Field | Value |
   | --- | --- |
   | PyPI Project Name | `singapore-mobile-proxy` |
   | Owner | `Xavierfok` (capital X) |
   | Repository name | `singapore-mobile-proxy` |
   | Workflow name | `publish.yml` |
   | Environment name | `pypi` |

3. Click **Add**. The project is created on PyPI by the first successful publish.

The `pypi` environment already exists in the GitHub repo settings. Optionally add yourself as a
required reviewer there, so each release waits for a click.

## Each release

1. Bump `__version__` in `src/singapore_mobile_proxy/__init__.py` and commit.
2. Tag and push: `git tag v0.1.0 && git push origin v0.1.0`.
3. The `publish` workflow runs the tests, checks the tag matches the version, rewrites the README's
   `utm_source=github&utm_medium=repo` links to `utm_source=pypi&utm_medium=directory`, builds,
   runs `twine check`, and uploads.

PyPI never accepts the same version twice, so a failed upload after a partial success needs a new
version number.
