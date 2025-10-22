import streamlit as st
import google.generativeai as genai
from PyPDF2 import PdfReader
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import os
from dotenv import load_dotenv

# .env dosyasından API anahtarını yükle
load_dotenv()

# Sayfa yapılandırması
st.set_page_config(
    page_title="Anayasa Chatbot",
    page_icon="📖",
    layout="centered"
)

# Başlık
st.title("📖 Anayasa Chatbot")
st.markdown("Anayasa hakkında sorularınızı sorun!")

# API anahtarını al
api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    st.error("⚠️ GOOGLE_API_KEY bulunamadı! Lütfen .env dosyanızı kontrol edin.")
    st.stop()

# Google Gemini API'yi yapılandır
genai.configure(api_key=api_key)

# PDF okuma ve işleme fonksiyonu
@st.cache_resource
def load_pdf_and_embeddings(pdf_path):
    """PDF'i okur, metni parçalara ayırır ve embeddings oluşturur"""
    try:
        # PDF'i oku
        reader = PdfReader(pdf_path)
        full_text = ""
        
        for page in reader.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
        
        # Metni paragraf bazında parçalara ayır
        # Boş satırları temizle ve anlamlı parçalar oluştur
        paragraphs = [p.strip() for p in full_text.split('\n\n') if p.strip()]
        
        # Çok kısa parçaları birleştir
        chunks = []
        current_chunk = ""
        min_chunk_size = 200  # Minimum karakter sayısı
        
        for para in paragraphs:
            if len(current_chunk) + len(para) < min_chunk_size:
                current_chunk += " " + para
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = para
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        # Embedding modeli yükle (Türkçe destekli model)
        model = SentenceTransformer('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')
        
        # Her parça için embedding oluştur
        embeddings = model.encode(chunks)
        
        return chunks, embeddings, model
        
    except Exception as e:
        st.error(f"PDF yüklenirken hata oluştu: {str(e)}")
        return None, None, None

# Alakalı parçaları bulma fonksiyonu
def find_relevant_chunks(query, chunks, embeddings, model, top_k=3):
    """Sorguya en alakalı PDF parçalarını bulur"""
    # Sorgu için embedding oluştur
    query_embedding = model.encode([query])
    
    # Cosine similarity hesapla
    similarities = cosine_similarity(query_embedding, embeddings)[0]
    
    # En yüksek skorlu parçaları al
    top_indices = np.argsort(similarities)[-top_k:][::-1]
    
    relevant_chunks = [chunks[i] for i in top_indices]
    relevant_scores = [similarities[i] for i in top_indices]
    
    return relevant_chunks, relevant_scores

# Gemini ile cevap üret
def generate_answer(query, context_chunks):
    """Gemini kullanarak soruya cevap üretir"""
    try:
        # Gemini modeli (en güncel stable model)
        model = genai.GenerativeModel('gemini-2.0-flash')
        
        # Context'i birleştir
        context = "\n\n".join([f"Bölüm {i+1}:\n{chunk}" for i, chunk in enumerate(context_chunks)])
        
        # Prompt oluştur
        prompt = f"""Sen bir Anayasa uzmanısın. Aşağıda verilen Anayasa metinlerini kullanarak kullanıcının sorusuna cevap ver.

ÖNEMLI: Sadece verilen metinlere dayanarak cevap ver. Eğer metinlerde cevap yoksa, "Bu konu hakkında verilen metinlerde bilgi bulamadım." şeklinde yanıt ver.

Anayasa Metinleri:
{context}

Kullanıcı Sorusu: {query}

Cevabın açık, anlaşılır ve profesyonel olsun. Gerekirse metinden alıntı yap."""

        # Cevap üret
        response = model.generate_content(prompt)
        
        return response.text
        
    except Exception as e:
        return f"Cevap üretilirken hata oluştu: {str(e)}"

# Ana uygulama
def main():
    pdf_path = "data/anayasa.pdf"
    
    # PDF'i kontrol et
    if not os.path.exists(pdf_path):
        st.error(f"⚠️ PDF dosyası bulunamadı: {pdf_path}")
        st.info("Lütfen 'data' klasörüne 'anayasa.pdf' dosyasını ekleyin.")
        st.stop()
    
    # PDF'i yükle ve embeddings oluştur (cache'lenmiş)
    with st.spinner("📚 Anayasa yükleniyor ve işleniyor..."):
        chunks, embeddings, model = load_pdf_and_embeddings(pdf_path)
    
    if chunks is None:
        st.stop()
    
    st.success(f"✅ Anayasa yüklendi! ({len(chunks)} bölüm işlendi)")
    
    # Chat geçmişi için session state
    if "messages" not in st.session_state:
        st.session_state.messages = []
    
    # Chat geçmişini göster
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Kullanıcı inputu
    if prompt := st.chat_input("Anayasa hakkında bir soru sorun..."):
        # Kullanıcı mesajını göster ve kaydet
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Asistan cevabı
        with st.chat_message("assistant"):
            with st.spinner("🔍 Anayasa'da arıyorum..."):
                # Alakalı parçaları bul
                relevant_chunks, scores = find_relevant_chunks(
                    prompt, chunks, embeddings, model, top_k=3
                )
                
                # Gemini ile cevap üret
                answer = generate_answer(prompt, relevant_chunks)
                
                st.markdown(answer)
                
                # Kaynak bilgisini göster (expander içinde)
                with st.expander("📑 Kullanılan Kaynak Metinler"):
                    for i, (chunk, score) in enumerate(zip(relevant_chunks, scores)):
                        st.markdown(f"**Bölüm {i+1}** (Benzerlik: {score:.2%})")
                        st.text(chunk[:300] + "..." if len(chunk) > 300 else chunk)
                        st.divider()
        
        # Asistan mesajını kaydet
        st.session_state.messages.append({"role": "assistant", "content": answer})
    
    # Sidebar bilgiler
    with st.sidebar:
        st.header("ℹ️ Hakkında")
        st.markdown("""
        Bu chatbot, Türkiye Cumhuriyeti Anayasası hakkında 
        sorularınızı yanıtlamak için tasarlanmıştır.
        
        **Nasıl Çalışır?**
        1. Sorunuz Anayasa metninde aranır
        2. En alakalı bölümler bulunur
        3. Google Gemini AI bu bölümleri kullanarak cevap verir
        
        **Teknolojiler:**
        - 🎨 Streamlit
        - 🤖 Google Gemini AI
        - 🔍 Semantic Search
        - 📄 PDF Processing
        """)
        
        if st.button("🗑️ Sohbeti Temizle"):
            st.session_state.messages = []
            st.rerun()

if __name__ == "__main__":
    main()
