import base64
import json
import os
import pathlib
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request

OWNER = 'ckstock'
GH = os.environ['GH_MIRROR_TOKEN']
GT = os.environ['GITEE_TOKEN']
os.environ['GIT_TERMINAL_PROMPT'] = '0'
os.environ['GIT_LFS_SKIP_SMUDGE'] = '1'


def api(host, path, params=None):
    params = dict(params or {})
    headers = {'Accept': 'application/vnd.github+json'} if host == 'github' else {}
    root = 'https://api.github.com' if host == 'github' else 'https://gitee.com/api/v5'
    if host == 'github':
        headers['Authorization'] = 'Bearer ' + GH
    else:
        params['access_token'] = GT
    url = root + path + ('?' + urllib.parse.urlencode(params) if params else '')
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=90) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError('API HTTP ' + str(e.code)) from None


def pages(host, path, params=None):
    result = []
    for page in range(1, 10001):
        batch = api(host, path, dict(params or {}, per_page=100, page=page))
        if not isinstance(batch, list):
            raise RuntimeError('Unexpected API response')
        result.extend(batch)
        if len(batch) < 100:
            return result
    raise RuntimeError('Pagination limit')


def git(args, cwd=None, host=None, allow_failure=False):
    cmd = ['git']
    if host:
        token = GH if host == 'github' else GT
        user = 'x-access-token' if host == 'github' else 'oauth2'
        auth = base64.b64encode((user + ':' + token).encode()).decode()
        cmd += ['-c', 'http.extraheader=Authorization: Basic ' + auth]
    p = subprocess.run(cmd + args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if p.returncode and not allow_failure:
        # Do not expose private URLs, branch names, or authentication headers.
        raise RuntimeError('Git operation failed: ' + args[0])
    return p


def save(root, name, data):
    (root / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    source = [r for r in pages('github', '/user/repos', {'affiliation': 'owner'})
              if r['owner']['login'] == OWNER]
    if api('gitee', '/user')['login'] != OWNER:
        raise RuntimeError('Gitee credential owner mismatch')
    targets = pages('gitee', '/user/repos', {'type': 'owner'})
    totals = {'repositories': len(source), 'archived': 0, 'pull_requests': 0,
              'wiki_copied': 0, 'wiki_absent': 0, 'lfs_repositories': 0}
    for index, repo in enumerate(source, 1):
        name = repo['name']
        print('::add-mask::' + name, flush=True)
        exact = [r for r in targets if r['path'] == name]
        candidates = exact or [r for r in targets if r['name'].lower() == name.lower()]
        if len(candidates) != 1:
            raise RuntimeError('Missing or ambiguous target at repository ' + str(index))
        target = api('gitee', '/repos/' + OWNER + '/' + candidates[0]['path'])
        if repo['private'] and not target['private']:
            raise RuntimeError('Private source has public target')
        target_path = target['path']
        print('::add-mask::' + target_path, flush=True)
        source_url = 'https://github.com/' + OWNER + '/' + name
        target_url = 'https://gitee.com/' + OWNER + '/' + target_path
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            git(['init', '-q', '-b', 'github-metadata-backup'], td)
            git(['config', 'user.name', 'GitHub backup'], td)
            git(['config', 'user.email', 'backup@users.noreply.github.com'], td)
            existing = git(['ls-remote', target_url + '.git', 'refs/heads/github-metadata-backup'], host='gitee').stdout.strip()
            if existing:
                git(['fetch', '-q', target_url + '.git', 'refs/heads/github-metadata-backup'], td, 'gitee')
                git(['checkout', '-q', '-B', 'github-metadata-backup', 'FETCH_HEAD'], td)
                if not (root / 'BACKUP-OWNERSHIP.json').exists():
                    raise RuntimeError('Backup branch exists without ownership marker')
                marker = json.loads((root / 'BACKUP-OWNERSHIP.json').read_text())
                if marker.get('source') != source_url:
                    raise RuntimeError('Backup branch ownership mismatch')
            save(root, 'BACKUP-OWNERSHIP.json', {'source': source_url, 'format': 1})
            save(root, 'repository.json', repo)
            issues = pages('github', '/repos/' + OWNER + '/' + name + '/issues', {'state': 'all'})
            save(root, 'issues.json', issues)
            pulls = pages('github', '/repos/' + OWNER + '/' + name + '/pulls', {'state': 'all'})
            records = []
            for pr in pulls:
                endpoint = '/repos/' + OWNER + '/' + name
                number = str(pr['number'])
                records.append({'pull': api('github', endpoint + '/pulls/' + number),
                    'comments': pages('github', endpoint + '/issues/' + number + '/comments'),
                    'reviews': pages('github', endpoint + '/pulls/' + number + '/reviews'),
                    'review_comments': pages('github', endpoint + '/pulls/' + number + '/comments'),
                    'commits': pages('github', endpoint + '/pulls/' + number + '/commits'),
                    'files': pages('github', endpoint + '/pulls/' + number + '/files')})
            save(root, 'pull-requests.json', records)
            releases = pages('github', '/repos/' + OWNER + '/' + name + '/releases')
            save(root, 'releases.json', releases)
            save(root, 'labels.json', pages('github', '/repos/' + OWNER + '/' + name + '/labels'))
            save(root, 'milestones.json', pages('github', '/repos/' + OWNER + '/' + name + '/milestones', {'state': 'all'}))
            save(root, 'backup-manifest.json', {'source': source_url, 'issues': len([i for i in issues if 'pull_request' not in i]),
                'pull_requests': len(pulls), 'releases': len(releases), 'authority': 'GitHub'})
            if any(r.get('assets') for r in releases):
                raise RuntimeError('Release assets require binary backup support')
            if any('pull_request' not in item for item in issues):
                raise RuntimeError('Issue comment backup requires extension')
            (root / 'README.md').write_text('# GitHub metadata backup\n\nSource: ' + source_url +
                '\n\nThis branch preserves original GitHub JSON, authors, timestamps and URLs. '
                'It does not recreate discussions as Gitee posts. The default code branch is unchanged.\n', encoding='utf-8')
            git(['add', '.'], td)
            if git(['diff', '--cached', '--quiet'], td, allow_failure=True).returncode:
                git(['commit', '-qm', 'Update GitHub metadata backup'], td)
                git(['push', '-q', target_url + '.git', 'HEAD:refs/heads/github-metadata-backup'], td, 'gitee')
            local = git(['rev-parse', 'HEAD'], td).stdout.strip()
            remote = git(['ls-remote', target_url + '.git', 'refs/heads/github-metadata-backup'], host='gitee').stdout.split()[0]
            if local != remote:
                raise RuntimeError('Metadata read-back verification failed')
            wiki_state = 'disabled'
            if repo.get('has_wiki'):
                # HTTP 404/no repository is common for an enabled but never created wiki.
                probe = git(['ls-remote', source_url + '.wiki.git'], host='github', allow_failure=True)
                if probe.returncode:
                    text = probe.stderr.decode(errors='replace').lower()
                    if 'repository not found' not in text and 'not found' not in text:
                        raise RuntimeError('Wiki probe failed')
                    wiki_state = 'absent'
                    totals['wiki_absent'] += 1
                elif probe.stdout.strip():
                    wiki = root / 'wiki.git'
                    git(['clone', '--bare', '-q', source_url + '.wiki.git', str(wiki)], host='github')
                    # Store complete wiki history in a separate target branch; no Gitee wiki capability assumption.
                    refs = git(['for-each-ref', '--format=%(refname)', 'refs/heads'], str(wiki)).stdout.decode().splitlines()
                    for ref in refs:
                        dest = 'refs/heads/github-wiki-backup/' + ref.removeprefix('refs/heads/')
                        git(['push', '-q', target_url + '.git', ref + ':' + dest], str(wiki), 'gitee')
                    wiki_state = 'copied'
                    totals['wiki_copied'] += 1
                else:
                    wiki_state = 'empty'
            totals['archived'] += 1
            totals['pull_requests'] += len(pulls)
            print('Repository ' + str(index) + ': metadata verified; PRs=' + str(len(pulls)) + '; wiki=' + wiki_state, flush=True)
    print('BACKUP_SUMMARY ' + json.dumps(totals), flush=True)


if __name__ == '__main__':
    main()
