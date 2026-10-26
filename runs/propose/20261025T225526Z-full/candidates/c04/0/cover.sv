module cov_P4 (
  input logic       clk,
  input logic       rst,
  input logic       busy,
  input logic       m_axis_tvalid,
  input logic [7:0] m_axis_tdata
);

  // 0: idle
  // 1: reset seen while busy with a pending word
  // 2: out of reset with tvalid and busy low
  reg [1:0] st;

  always @(posedge clk) begin
    if (rst) begin
      if (busy && m_axis_tvalid) st <= 2'd1;
      else if (st == 2'd2) st <= 2'd0;
    end else begin
      if (st == 2'd1 && !m_axis_tvalid && !busy) st <= 2'd2;
    end
  end

  P4_rst_mid_frame_pending: cover property (@(posedge clk)
    st == 2'd2 && !rst && m_axis_tvalid && m_axis_tdata == 8'hA5);

endmodule

bind uart_rx cov_P4 u_cov_P4 (.*);
