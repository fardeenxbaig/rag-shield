# Contributing to RAG Shield

Thank you for your interest in contributing! 

## How to Contribute

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/your-feature-name`
3. **Make your changes**
4. **Test thoroughly** - Deploy and test both SingleBucket and DualBucket modes
5. **Commit with clear messages**: `git commit -m "Add: feature description"`
6. **Push to your fork**: `git push origin feature/your-feature-name`
7. **Open a Pull Request**

## Code Standards

- Follow existing code style
- Add comments for complex logic
- Update documentation for new features
- Include test cases when applicable

## Testing

Before submitting:
- [ ] CloudFormation template validates
- [ ] Lambda function syntax is correct
- [ ] Clean files are tagged correctly
- [ ] Malicious files are quarantined
- [ ] Documentation is updated

## Reporting Issues

- Use GitHub Issues
- Include CloudFormation stack events for deployment issues
- Include Lambda logs for runtime errors
- Specify deployment mode (SingleBucket/DualBucket)

## Questions?

Open a GitHub Discussion or Issue.
