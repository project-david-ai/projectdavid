const stable = ["main", "master"].includes(process.env.GITHUB_REF_NAME);

module.exports = {
  branches: ["main", "master", { name: "dev", prerelease: true }],
  plugins: [
    "@semantic-release/commit-analyzer",
    "@semantic-release/release-notes-generator",
    ...(stable ? [["@semantic-release/changelog", { changelogFile: "CHANGELOG.md" }]] : []),
    ["@semantic-release/exec", {
      prepareCmd: "python scripts/update_version.py ${nextRelease.version} pyproject.toml",
    }],
    "@semantic-release/github",
    ...(stable ? [["@semantic-release/git", {
      assets: ["CHANGELOG.md", "pyproject.toml"],
      message: "chore(release): ${nextRelease.version} [skip ci]\n\n${nextRelease.notes}",
    }]] : []),
  ],
};
