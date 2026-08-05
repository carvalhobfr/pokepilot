import os
from pathlib import Path

class KnowledgeBase:
    """
    Simple RAG (Retrieval Augmented Generation) system for Pokemon AI.
    Currently uses keyword matching, but designed to be upgraded to Vector Search (ChromaDB).
    """
    
    def __init__(self, knowledge_dir="docs/knowledge"):
        self.knowledge_dir = Path(knowledge_dir)
        self.documents = []
        self.load_documents()
        
    def load_documents(self):
        """Loads all text files from the knowledge directory."""
        if not self.knowledge_dir.exists():
            print(f"Knowledge dir {self.knowledge_dir} not found.")
            return

        self.documents = []
        for file_path in self.knowledge_dir.glob("*.txt"):
            with open(file_path, 'r') as f:
                content = f.read()
                # Split by lines or paragraphs for better granularity
                lines = [line.strip() for line in content.split('\n') if line.strip()]
                for line in lines:
                    self.documents.append({
                        "source": file_path.name,
                        "content": line
                    })
        print(f"Loaded {len(self.documents)} knowledge snippets.")

    def search(self, query, limit=3):
        """
        Searches for relevant information.
        TODO: Replace with Vector Embedding search (OpenAI/SentenceTransformers + ChromaDB).
        """
        query_terms = query.lower().split()
        results = []
        
        for doc in self.documents:
            content_lower = doc["content"].lower()
            score = 0
            for term in query_terms:
                if term in content_lower:
                    score += 1
            
            if score > 0:
                results.append((score, doc))
        
        # Sort by score desc
        results.sort(key=lambda x: x[0], reverse=True)
        
        return [r[1] for r in results[:limit]]

if __name__ == "__main__":
    # Test
    kb = KnowledgeBase()
    print("Search 'Surf':", kb.search("Where is Surf?"))
    print("Search 'Brock':", kb.search("How to beat Brock"))
