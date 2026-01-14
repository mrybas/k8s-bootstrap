# GitLab setup script for E2E tests
# Run with: gitlab-rails runner /scripts/gitlab-setup.rb
#
# Creates:
# - Personal Access Token for root
# - Public repository
# - Private repository with deploy token

require 'json'

OUTPUT_DIR = '/tmp/gitlab-init'
FileUtils.mkdir_p(OUTPUT_DIR)

puts "=== GitLab E2E Test Setup ==="

# 1. Create PAT for root user
puts "\n--- Creating Personal Access Token for root ---"
root = User.find_by_username('root')

# Delete existing test token if present
existing_token = root.personal_access_tokens.find_by(name: 'e2e-test-token')
existing_token&.revoke!

root_token = root.personal_access_tokens.create!(
  name: 'e2e-test-token',
  scopes: [:api, :read_repository, :write_repository],
  expires_at: 1.year.from_now
)
puts "Root PAT created: #{root_token.token[0..15]}..."
File.write("#{OUTPUT_DIR}/root_pat.txt", root_token.token)

# 2. Create public repository
puts "\n--- Creating public repository ---"
public_project = Project.find_by_full_path('root/public-repo')
unless public_project
  public_project = Projects::CreateService.new(
    root,
    {
      name: 'public-repo',
      path: 'public-repo',
      description: 'Public test repository for E2E tests',
      visibility_level: Gitlab::VisibilityLevel::PUBLIC,
      initialize_with_readme: true
    }
  ).execute
  
  if public_project.persisted?
    puts "Created public repo: #{public_project.full_path}"
  else
    puts "ERROR creating public repo: #{public_project.errors.full_messages.join(', ')}"
  end
else
  puts "Public repo already exists: #{public_project.full_path}"
end

File.write("#{OUTPUT_DIR}/public_project_id.txt", public_project.id.to_s)
File.write("#{OUTPUT_DIR}/public_project_path.txt", public_project.full_path)

# 3. Create private repository
puts "\n--- Creating private repository ---"
private_project = Project.find_by_full_path('root/private-repo')
unless private_project
  private_project = Projects::CreateService.new(
    root,
    {
      name: 'private-repo',
      path: 'private-repo',
      description: 'Private test repository for E2E tests',
      visibility_level: Gitlab::VisibilityLevel::PRIVATE,
      initialize_with_readme: true
    }
  ).execute
  
  if private_project.persisted?
    puts "Created private repo: #{private_project.full_path}"
  else
    puts "ERROR creating private repo: #{private_project.errors.full_messages.join(', ')}"
  end
else
  puts "Private repo already exists: #{private_project.full_path}"
end

File.write("#{OUTPUT_DIR}/private_project_id.txt", private_project.id.to_s)
File.write("#{OUTPUT_DIR}/private_project_path.txt", private_project.full_path)

# 4. Unprotect main branch for testing (allows force push)
puts "\n--- Unprotecting main branch for testing ---"
[public_project, private_project].each do |project|
  next unless project.persisted?
  
  # Remove branch protection for main
  protected_branch = project.protected_branches.find_by(name: 'main')
  if protected_branch
    protected_branch.destroy
    puts "Unprotected main branch in: #{project.full_path}"
  end
end

# Summary
puts "\n=== Setup Complete ==="
puts "Files saved to: #{OUTPUT_DIR}/"
puts ""
puts "Available credentials:"
puts "  Root PAT: #{OUTPUT_DIR}/root_pat.txt"
puts ""
puts "Repositories:"
puts "  Public:  http://gitlab/root/public-repo.git"
puts "  Private: http://gitlab/root/private-repo.git"
puts ""
puts "Test API access:"
puts "  curl -H 'PRIVATE-TOKEN: <token>' http://localhost:8080/api/v4/projects"
