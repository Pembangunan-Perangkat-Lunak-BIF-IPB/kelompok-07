FROM mambaorg/micromamba:1.5.10

ARG MAMBA_DOCKERFILE_ACTIVATE=1
ARG SNPEFF_DB=Escherichia_coli_str_k_12_substr_mg1655_gca_000005845

# Tool bioinformatika + Python (versi dikunci di sini agar sama di semua perangkat)
RUN micromamba install -y -n base -c conda-forge -c bioconda \
      python=3.11 fastqc fastp bwa samtools bcftools snpeff \
    && micromamba clean --all --yes

WORKDIR /app

USER root
RUN mkdir -p /app/data && chown -R $MAMBA_USER:$MAMBA_USER /app
USER $MAMBA_USER

COPY --chown=$MAMBA_USER:$MAMBA_USER requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Unduh database anotasi sekali saat build
RUN snpEff download ${SNPEFF_DB}

COPY --chown=$MAMBA_USER:$MAMBA_USER . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
